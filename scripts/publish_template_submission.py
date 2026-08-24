# -*- coding: utf-8 -*-
"""2026-08-24 功能：驗證 GitHub Issue 投稿 ZIP，核准後轉為社群模板並準備自動發布。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from build_template_index import write_index


SHARE_FORMAT = "CPA_TEMPLATE_SHARE"
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 4 * 1024 * 1024
SENSITIVE_KEYS = {"sample_path", "_online", "_source_sheet_override", "_sheet_locked_by_source"}
ALLOWED_MODES = {"header_map", "sectioned_ledger", "paged_ledger", "print_ledger_txt", "excel_xml_ledger"}


def _slug(value: str, fallback: str) -> str:
    text = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(value or "").strip()).strip("._-")
    return (text or fallback)[:70]


def _canonical_templates(templates: list[dict]) -> str:
    return json.dumps(templates, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _find_zip_url(issue_body: str) -> str:
    patterns = [
        r"\[[^\]]+\.zip\]\((https://github\.com/user-attachments/(?:files|assets)/[^)]+)\)",
        r"(https://github\.com/user-attachments/(?:files|assets)/[^\s)>]+)",
    ]
    urls = []
    for pattern in patterns:
        urls.extend(re.findall(pattern, issue_body or "", flags=re.IGNORECASE))
    if not urls:
        raise ValueError("投稿 Issue 中找不到 ZIP 附件；請先附加程式產生的 .zip。")
    return urls[-1].rstrip(".,")


def _download_zip(url: str, target: Path) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or not parsed.path.startswith("/user-attachments/"):
        raise ValueError("附件網址不是 GitHub user-attachments。")
    req = urllib.request.Request(url, headers={"User-Agent": "CPA-template-review-bot"})
    with urllib.request.urlopen(req, timeout=30) as response, target.open("wb") as fh:
        total = 0
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise ValueError("投稿 ZIP 超過 8 MB 限制。")
            fh.write(chunk)


def _read_submission_zip(path: Path) -> list[dict]:
    if not zipfile.is_zipfile(path):
        raise ValueError("附件不是有效的 ZIP。")
    with zipfile.ZipFile(path) as zf:
        members = [x for x in zf.infolist() if not x.is_dir()]
        if len(members) != 1 or not members[0].filename.lower().endswith(".cpatpl"):
            raise ValueError("投稿 ZIP 必須且只能包含一個 .cpatpl。")
        info = members[0]
        member_path = Path(info.filename)
        if member_path.name != info.filename or ".." in member_path.parts:
            raise ValueError("ZIP 內含不安全路徑。")
        if info.file_size > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("投稿內容解壓後超過 4 MB 限制。")
        if info.flag_bits & 0x1:
            raise ValueError("不接受加密 ZIP。")
        payload = json.loads(zf.read(info).decode("utf-8-sig"))

    if not isinstance(payload, dict) or payload.get("format") != SHARE_FORMAT:
        raise ValueError("內層檔案不是 CPA 模板分享格式。")
    templates = payload.get("templates")
    if not isinstance(templates, list) or not templates:
        raise ValueError("投稿內容沒有模板。")
    expected = str(payload.get("checksum_sha256") or "")
    actual = hashlib.sha256(_canonical_templates(templates).encode("utf-8")).hexdigest()
    if not expected or expected != actual:
        raise ValueError("分享檔 checksum 不一致。")
    return templates


def _contains_private_path(value) -> bool:
    if isinstance(value, dict):
        return any(_contains_private_path(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_private_path(v) for v in value)
    if not isinstance(value, str):
        return False
    text = value.strip()
    return bool(
        re.search(r"(?:^|\s)[A-Za-z]:[\\/]", text)
        or text.startswith("\\\\")
        or re.search(r"/(?:Users|home)/[^/]+/", text, flags=re.IGNORECASE)
    )


def _validate_and_sanitize(tpl: dict) -> dict:
    if not isinstance(tpl, dict):
        raise ValueError("模板內容不是 JSON 物件。")
    clean = copy.deepcopy(tpl)
    for key in SENSITIVE_KEYS:
        clean.pop(key, None)
    if _contains_private_path(clean):
        raise ValueError(f"模板「{clean.get('name') or clean.get('id') or '未命名'}」仍含本機或網路路徑。")
    mode = str(clean.get("mode") or "header_map").strip()
    if mode not in ALLOWED_MODES:
        raise ValueError(f"不支援的模板模式：{mode}")
    if not any(key in clean for key in ("columns", "mode", "header_row", "data_start_row")):
        raise ValueError("模板缺少解析設定。")
    if mode == "header_map":
        columns = clean.get("columns")
        if not isinstance(columns, dict):
            raise ValueError("header_map 模板缺少 columns。")
        required = ["vno", "summary", "account_name", "debit", "credit"]
        missing = [key for key in required if not str(columns.get(key) or "").strip()]
        date_mode = str(clean.get("date_mode") or "").lower()
        has_date = bool(str(columns.get("date") or "").strip())
        has_month_day = date_mode in {"md", "month_day", "monthday"} and clean.get("date_month_col") and clean.get("date_day_col")
        if missing or not (has_date or has_month_day):
            labels = missing + ([] if (has_date or has_month_day) else ["date"])
            raise ValueError("header_map 模板缺少必要欄位：" + ", ".join(labels))
    return clean


def _community_id(author: str, source_id: str) -> str:
    author_slug = _slug(author, "user")
    source_slug = _slug(source_id, "template")
    prefix = f"community_{author_slug}_"
    if source_slug.startswith(prefix):
        return source_slug[:120]
    return f"{prefix}{source_slug}"[:120]


def _bootstrap_official_templates(repo_root: Path) -> int:
    """第一次啟用自動發布時，依封裝索引複製既有正式模板，避免重建 index 遺失舊項目。"""
    source_index = repo_root / "import_templates" / "index.json"
    if not source_index.exists():
        return 0
    data = json.loads(source_index.read_text(encoding="utf-8-sig"))
    copied = 0
    for item in data.get("templates", []):
        rel = str(item.get("file") or "")
        if not rel.startswith("templates/") or not rel.endswith(".json"):
            continue
        source = repo_root / "import_templates" / rel
        target = repo_root / rel
        if source.exists() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied += 1
    return copied


def prepare(event_path: Path, repo_root: Path, publish: bool) -> tuple[list[dict], list[str]]:
    event = json.loads(event_path.read_text(encoding="utf-8"))
    issue = event.get("issue") or {}
    body = str(issue.get("body") or "")
    author = str((issue.get("user") or {}).get("login") or "unknown")
    url = _find_zip_url(body)

    with tempfile.TemporaryDirectory() as td:
        zip_path = Path(td) / "submission.zip"
        _download_zip(url, zip_path)
        raw_templates = _read_submission_zip(zip_path)

    prepared = []
    report = []
    publish_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for raw in raw_templates:
        clean = _validate_and_sanitize(raw)
        source_id = str(clean.get("id") or "template").strip()
        final_id = _community_id(author, source_id)
        base_name = str(clean.get("name") or source_id).strip()
        clean["id"] = final_id
        if "（社群：" not in base_name:
            clean["name"] = f"{base_name}（社群：{author}）"
        clean["updated_at"] = publish_date
        prepared.append(clean)
        report.append(f"- `{final_id}`：{clean['name']}（{clean.get('mode', 'header_map')}）")

    if publish:
        _bootstrap_official_templates(repo_root)
        target_dir = repo_root / "templates"
        target_dir.mkdir(parents=True, exist_ok=True)
        for tpl in prepared:
            target = target_dir / f"{tpl['id']}.json"
            target.write_text(json.dumps(tpl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_index(repo_root)

    return prepared, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--mode", choices=("validate", "publish"), required=True)
    parser.add_argument("--report-file", required=True)
    args = parser.parse_args()
    report_path = Path(args.report_file)
    try:
        prepared, lines = prepare(
            Path(args.event),
            Path(args.repo_root).resolve(),
            publish=args.mode == "publish",
        )
        heading = "✅ 投稿驗證通過" if args.mode == "validate" else "✅ 模板已準備發布"
        report_path.write_text(
            heading + f"\n\n共 {len(prepared)} 個模板：\n" + "\n".join(lines)
            + "\n\n已檢查分享檔 checksum、ZIP 安全性、隱私路徑、模板模式與必要欄位。\n",
            encoding="utf-8",
        )
    except Exception as exc:
        report_path.write_text(f"❌ 投稿驗證失敗\n\n{exc}\n", encoding="utf-8")
        print(str(exc), file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
