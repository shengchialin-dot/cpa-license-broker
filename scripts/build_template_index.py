# -*- coding: utf-8 -*-
"""2026-08-24 功能：掃描正式 templates/*.json 並完整重建線上模板 index.json。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


RESERVED_NAMES = {"settings.json", "index.json", "_online_template_install.json"}


def build_index(repo_root: Path) -> dict:
    template_dir = repo_root / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    items = []
    seen_ids = set()

    for path in sorted(template_dir.glob("*.json")):
        if path.name.lower() in RESERVED_NAMES:
            continue
        with path.open("r", encoding="utf-8-sig") as fh:
            tpl = json.load(fh)
        if not isinstance(tpl, dict):
            raise ValueError(f"{path.name} 不是 JSON 物件。")
        template_id = str(tpl.get("id") or path.stem).strip()
        if not template_id:
            raise ValueError(f"{path.name} 缺少模板 ID。")
        if template_id in seen_ids:
            raise ValueError(f"模板 ID 重複：{template_id}")
        seen_ids.add(template_id)
        items.append({
            "id": template_id,
            "name": tpl.get("name") or template_id,
            "mode": tpl.get("mode", ""),
            "file_type": tpl.get("file_type", ""),
            "sheet": tpl.get("sheet", ""),
            "updated_at": tpl.get("updated_at", ""),
            "file": f"templates/{path.name}",
        })

    items.sort(key=lambda x: (str(x.get("name") or "").casefold(), x["id"]))
    return {"templates": items}


def write_index(repo_root: Path) -> Path:
    index_path = repo_root / "index.json"
    data = build_index(repo_root)
    index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    path = write_index(Path(args.repo_root).resolve())
    print(f"已重建 {path}")


if __name__ == "__main__":
    main()
