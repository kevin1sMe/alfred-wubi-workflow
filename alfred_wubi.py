#!/usr/bin/env python3
"""Alfred Script Filter: query wangma wubi codes and component images.

Usage:
  python3 alfred_wubi.py <char> [--max-retry N] [--cache-dir DIR]

The script outputs Alfred JSON items:
  - A summary row of codes.
  - Rows for component images (6/9-key numeric and wubi 86/98/new century), using
    the first image as the item icon and quicklook URL.

Dependencies: requests, pillow, bs4 (already required by wubi_query.py).
"""

import argparse
import json
from pathlib import Path

import wubi_query


VALID_FILTERS = {
    "summary",
    "num5",
    "num6",
    "num9",
    "wb86",
    "wb98",
    "wbx",
    "strokes",
    "num6_parts",
    "num9_parts",
    "wb86_parts",
    "wb98_parts",
    "wbx_parts",
}


def build_items(ch: str, codes: dict, cache_dir: Path, filters: set | None) -> list:
    items = []

    def allowed(key: str) -> bool:
        return filters is None or key in filters

    def code(key: str, default: str = "-") -> str:
        return codes.get(key, default)

    # Summary item（按 filters 控制字段）
    if allowed("summary"):
        summary_parts = []
        fields = [
            ("86", "wb86", "wb86"),
            ("98", "wb98", "wb98"),
            ("XSJ", "wb_xsj", "wbx"),
            ("NUM5", "num5", "num5"),
            ("NUM6", "num6", "num6"),
            ("NUM9", "num9", "num9"),
            ("Strokes", "strokes", "strokes"),
        ]
        for label, key, flt in fields:
            if filters is None or flt in filters:
                summary_parts.append(f"{label}:{code(key)}")
        summary = "  ".join(summary_parts)
        items.append({
            "title": f"{ch} codes",
            "subtitle": summary,
            "valid": False,
        })

    # 单独的编码项（便于只展示某类编码）
    def add_code_item(title: str, key: str, flt: str):
        if not allowed(flt):
            return
        val = codes.get(key)
        if not val:
            return
        items.append({
            "title": title,
            "subtitle": val,
            "valid": False,
        })

    add_code_item("数王 5 键编码", "num5", "num5")
    add_code_item("数王 6 键编码", "num6", "num6")
    add_code_item("数王 9 键编码", "num9", "num9")
    add_code_item("五笔 86 版本完整编码", "wb86", "wb86")
    add_code_item("五笔 98 版本完整编码", "wb98", "wb98")
    add_code_item("五笔 新世纪版本完整编码", "wb_xsj", "wbx")
    add_code_item("笔画序列", "strokes", "strokes")

    def add_component(title: str, key: str, flt: str):
        if not allowed(flt):
            return
        imgs = codes.get(key) or []
        if not imgs:
            return
        local_map = wubi_query.download_components({key: imgs}, cache_dir)
        local_imgs = local_map.get(key, [])
        if not local_imgs:
            return
        for idx, p in enumerate(local_imgs, 1):
            items.append({
                "title": f"{title} [{idx}/{len(local_imgs)}]",
                "subtitle": Path(p).name,
                "arg": p,
                "icon": {"path": p},
                "quicklookurl": p,
                "valid": True,
            })

    add_component("Numeric 6-key parts", "num6_components", "num6_parts")
    add_component("Numeric 9-key parts", "num9_components", "num9_parts")
    add_component("Wubi 86 parts", "wb86_components", "wb86_parts")
    add_component("Wubi 98 parts", "wb98_components", "wb98_parts")
    add_component("Wubi XSJ parts", "wb_xsj_components", "wbx_parts")

    return items


def main():
    ap = argparse.ArgumentParser(description="Alfred Script Filter for wangma wubi query")
    ap.add_argument("char", help="single Chinese character")
    ap.add_argument("--max-retry", type=int, default=1, help="captcha retry limit")
    ap.add_argument("--cache-dir", type=Path, default=Path("alfred_cache"), help="where to store component images")
    ap.add_argument("--only", help="comma-separated filters (summary,num5,num6,num9,wb86,wb98,wbx,strokes,num6_parts,num9_parts,wb86_parts,wb98_parts,wbx_parts)")
    args = ap.parse_args()

    ch = args.char.strip()
    if len(ch) != 1:
        print(json.dumps({"items": [{"title": "Please input exactly one character", "subtitle": ch, "valid": False}]}))
        return

    cache_dir = args.cache_dir / ch
    cache_dir.mkdir(parents=True, exist_ok=True)

    filters = None
    if args.only:
        filters = set()
        for f in args.only.split(','):
            f = f.strip().lower()
            if f and f in VALID_FILTERS:
                filters.add(f)

    try:
        solver = wubi_query.CaptchaSolver.from_dir()
        codes = wubi_query.query_char(ch, max_retry=args.max_retry, solver=solver)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"items": [{"title": "Query failed", "subtitle": str(e), "valid": False}]}))
        return

    items = build_items(ch, codes, cache_dir, filters)
    if not items:
        items = [{"title": "No data", "valid": False}]

    print(json.dumps({"items": items}, ensure_ascii=False))


if __name__ == "__main__":
    main()
