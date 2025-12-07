#!/usr/bin/env python3
"""
Captcha fetch / template-based OCR tester for wangma.com.cn.

Usage examples:
  # Download a batch of captchas to ./captchas
  python3 captcha_ocr_test.py fetch --count 20 --out captchas

  # Label downloaded images (prints ASCII preview, you can also open the bmp)
  python3 captcha_ocr_test.py label captchas/*.bmp

  # Build digit templates from labeled images into ./captcha_templates
  python3 captcha_ocr_test.py build-templates captchas/*.bmp

  # Evaluate recognition accuracy against labeled files
  python3 captcha_ocr_test.py eval captchas/*.bmp

  # Solve a single image or fetch one on the fly
  python3 captcha_ocr_test.py solve captchas/0001_1234.bmp
  python3 captcha_ocr_test.py solve --live

Conventions:
  - A labeled filename contains the 4-digit ground truth somewhere in the name,
    e.g. 0001_1234.bmp or vc0-9876.bmp. The last 4 consecutive digits are used.
  - Templates are stored under ./captcha_templates/{digit}.bmp (or digit-N.bmp when using append)
"""

import argparse
import io
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import requests
from PIL import Image

CAPTCHA_URL = "http://www.wangma.com.cn/include/v.asp"
SESSION_URL = "http://www.wangma.com.cn/query/wmhz1.asp"
TEMPLATE_DIR = Path("captcha_templates")


# ---------- image utils ----------

def binarize(im: Image.Image, bg_index: Optional[int] = None, min_dot_neighbors: int = 0) -> List[List[int]]:
    """Convert palette BMP to 0/1 mask with background autodetect and noise cleanup."""
    # Auto-detect the background as the most frequent palette entry if not provided.
    if bg_index is None:
        hist = im.convert("P").histogram()
        bg_index = max(range(len(hist)), key=lambda i: hist[i])

    mask = [
        [1 if im.getpixel((x, y)) != bg_index else 0 for x in range(im.width)]
        for y in range(im.height)
    ]

    # Remove tiny isolated dots that can split characters into multiple components.
    if min_dot_neighbors >= 0:
        h, w = len(mask), len(mask[0])
        cleaned = [row[:] for row in mask]
        for y in range(h):
            for x in range(w):
                if mask[y][x] == 0:
                    continue
                neighbors = sum(
                    mask[ny][nx]
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                    if 0 <= (nx := x + dx) < w and 0 <= (ny := y + dy) < h
                )
                if neighbors <= min_dot_neighbors:
                    cleaned[y][x] = 0
        mask = cleaned

    return mask


def connected_components(mask: List[List[int]], min_size: int = 8):
    """Return components as (bbox, pixels) sorted by x."""
    h, w = len(mask), len(mask[0])
    seen = [[False] * w for _ in range(h)]
    comps = []
    for y in range(h):
        for x in range(w):
            if seen[y][x] or mask[y][x] == 0:
                continue
            stack = [(x, y)]
            seen[y][x] = True
            pixels = []
            while stack:
                cx, cy = stack.pop()
                pixels.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] and mask[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if len(pixels) >= min_size:
                xs = [p[0] for p in pixels]
                ys = [p[1] for p in pixels]
                comps.append(((min(xs), min(ys), max(xs), max(ys)), pixels))
    comps.sort(key=lambda c: c[0][0])
    return comps


def normalize_component(mask: List[List[int]], target_size=(9, 11)) -> List[List[int]]:
    """Resize component mask to fixed size for template comparison."""
    im = Image.new("1", (len(mask[0]), len(mask)))
    for y, row in enumerate(mask):
        for x, v in enumerate(row):
            im.putpixel((x, y), 255 if v else 0)
    im = im.resize(target_size, Image.NEAREST)
    return [[1 if im.getpixel((x, y)) else 0 for x in range(target_size[0])] for y in range(target_size[1])]


def hamming(a: List[List[int]], b: List[List[int]]) -> int:
    return sum(aa != bb for ra, rb in zip(a, b) for aa, bb in zip(ra, rb))


def ascii_preview(im: Image.Image, fg_char="#", bg_char=".") -> str:
    bg = 15
    rows = []
    for y in range(im.height):
        row = "".join(fg_char if im.getpixel((x, y)) != bg else bg_char for x in range(im.width))
        rows.append(row)
    return "\n".join(rows)


# ---------- solver ----------

class CaptchaSolver:
    def __init__(self, templates: Dict[str, List[List[List[int]]]]):
        """
        templates: digit -> list of masks (2D 0/1 arrays), allowing multi-sample per digit.
        """
        self.templates = templates

    @classmethod
    def from_dir(cls, directory: Path = TEMPLATE_DIR):
        tpls: Dict[str, List[List[List[int]]]] = {}
        if not directory.exists():
            raise RuntimeError(f"Template dir {directory} not found, run build-templates first.")
        for p in directory.glob("*.bmp"):
            digit = p.stem[:1]
            tpls.setdefault(digit, []).append(binarize(Image.open(p)))
        if len(tpls) < 10:
            raise RuntimeError(f"Need at least one template per digit (0-9), found {len(tpls)} in {directory}")
        return cls(tpls)

    def solve(self, im: Image.Image) -> str:
        mask = binarize(im)
        comps = connected_components(mask)
        if len(comps) != 4:
            # Fallback: evenly slice into 4 regions to avoid hard failure when components merge.
            slice_w = im.width // 4
            fallback_comps = []
            for i in range(4):
                x0 = i * slice_w
                x1 = im.width - 1 if i == 3 else (i + 1) * slice_w - 1
                coords = [
                    (x, y)
                    for y in range(im.height)
                    for x in range(x0, x1 + 1)
                    if mask[y][x]
                ]
                if coords:
                    xs = [c[0] for c in coords]
                    ys = [c[1] for c in coords]
                    bbox = (min(xs), min(ys), max(xs), max(ys))
                else:
                    bbox = (x0, 0, x1, im.height - 1)
                fallback_comps.append((bbox, coords))
            comps = fallback_comps
        result = ""
        for bbox, _pix in comps:
            x0, y0, x1, y1 = bbox
            comp_mask = [[mask[y][x] for x in range(x0, x1 + 1)] for y in range(y0, y1 + 1)]
            norm = normalize_component(comp_mask)
            best_digit, best_score = None, 1e9
            for d, tpl_list in self.templates.items():
                for tpl in tpl_list:
                    score = hamming(norm, normalize_component(tpl))
                    if score < best_score:
                        best_digit, best_score = d, score
            if best_digit is None:
                raise RuntimeError("No templates matched")
            result += best_digit
        return result


# ---------- data helpers ----------

def fetch_captcha(session: requests.Session) -> bytes:
    session.get(SESSION_URL, timeout=10)  # prime session cookie
    r = session.get(CAPTCHA_URL, timeout=10)
    r.raise_for_status()
    return r.content


def extract_label(path: Path) -> str:
    # Use the *last* 4-digit group in the stem to avoid picking a serial prefix
    # (e.g. vc0001_4607.bmp -> 4607, not 0001).
    matches = re.findall(r"(\d{4})", path.stem)
    return matches[-1] if matches else ""


def save_templates_from_labeled(paths: Sequence[Path], outdir: Path = TEMPLATE_DIR, overwrite: bool = False, append: bool = False):
    outdir.mkdir(exist_ok=True)
    added = 0
    for p in paths:
        label = extract_label(p)
        if len(label) != 4:
            continue
        im = Image.open(p)
        mask = binarize(im)
        comps = connected_components(mask)
        if len(comps) != 4:
            continue
        for digit_char, (bbox, _pix) in zip(label, comps):
            if append:
                existing = sorted(outdir.glob(f"{digit_char}-*.bmp"))
                next_id = 1 + (int(existing[-1].stem.split("-")[1]) if existing else 0)
                dest = outdir / f"{digit_char}-{next_id}.bmp"
            else:
                dest = outdir / f"{digit_char}.bmp"
                if dest.exists() and not overwrite:
                    continue
            x0, y0, x1, y1 = bbox
            crop = im.crop((x0, y0, x1 + 1, y1 + 1))
            crop.save(dest)
            added += 1
    return added


def evaluate(paths: Sequence[Path]) -> Tuple[int, int, List[str], List[Path]]:
    solver = CaptchaSolver.from_dir()
    ok = 0
    total = 0
    errors = []
    failed_paths = []
    for p in paths:
        label = extract_label(p)
        if len(label) != 4:
            continue
        total += 1
        pred = solver.solve(Image.open(p))
        if pred == label:
            ok += 1
        else:
            errors.append(f"{p.name}: expected {label}, got {pred}")
            failed_paths.append(p)
    return ok, total, errors, failed_paths


# ---------- CLI ----------

def cmd_fetch(args):
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    sess = requests.Session()
    for i in range(args.count):
        img = fetch_captcha(sess)
        fname = outdir / f"vc{i:04d}.bmp"
        fname.write_bytes(img)
        print(f"saved {fname}")


def cmd_label(args):
    for name in args.files:
        p = Path(name)
        im = Image.open(p)
        print(f"\nFile: {p}")
        print(ascii_preview(im))
        code = input("Enter 4-digit code (or blank to skip): ").strip()
        if len(code) != 4:
            print("skip")
            continue
        new_name = p.with_name(f"{p.stem}_{code}{p.suffix}")
        p.rename(new_name)
        print(f"renamed -> {new_name}")


def cmd_build_templates(args):
    paths = [Path(p) for p in args.files]
    added = save_templates_from_labeled(paths, TEMPLATE_DIR, overwrite=args.overwrite, append=args.append)
    print(f"Templates written: {added}, dir: {TEMPLATE_DIR}")


def cmd_eval(args):
    paths = [Path(p) for p in args.files]
    ok, total, errors, failed_paths = evaluate(paths)
    print(f"Accuracy: {ok}/{total} ({(ok/total*100 if total else 0):.1f}%)")
    if errors:
        print("Errors:")
        for e in errors:
            print("  ", e)
    
    if args.save_failed and failed_paths:
        outdir = Path(args.save_failed)
        outdir.mkdir(parents=True, exist_ok=True)
        for p in failed_paths:
            dest = outdir / p.name
            shutil.copy2(p, dest)
        print(f"\nSaved {len(failed_paths)} failed case(s) to: {outdir.resolve()}")


def cmd_solve(args):
    solver = CaptchaSolver.from_dir()
    if args.live:
        sess = requests.Session()
        img_bytes = fetch_captcha(sess)
        im = Image.open(io.BytesIO(img_bytes))
        print(ascii_preview(im))
        print("Predicted:", solver.solve(im))
    else:
        p = Path(args.file)
        im = Image.open(p)
        print(ascii_preview(im))
        print("Predicted:", solver.solve(im))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(required=True)

    sp = sub.add_parser("fetch", help="download captchas")
    sp.add_argument("--count", type=int, default=5)
    sp.add_argument("--out", default="captchas")
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("label", help="label images; renames files with code")
    sp.add_argument("files", nargs="+")
    sp.set_defaults(func=cmd_label)

    sp = sub.add_parser("build-templates", help="create digit templates from labeled files")
    sp.add_argument("files", nargs="+")
    sp.add_argument("--overwrite", action="store_true", help="overwrite single template per digit")
    sp.add_argument("--append", action="store_true", help="keep multiple templates per digit (digit-1.bmp, digit-2.bmp, ...)")
    sp.set_defaults(func=cmd_build_templates)

    sp = sub.add_parser("eval", help="evaluate accuracy on labeled files")
    sp.add_argument("files", nargs="+")
    sp.add_argument("--save-failed", metavar="DIR", help="save failed cases to this directory")
    sp.set_defaults(func=cmd_eval)

    sp = sub.add_parser("solve", help="solve one image or live fetch")
    sp.add_argument("file", nargs="?", help="path to bmp")
    sp.add_argument("--live", action="store_true", help="fetch one captcha and solve")
    sp.set_defaults(func=cmd_solve)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
