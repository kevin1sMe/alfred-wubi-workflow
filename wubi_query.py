#!/usr/bin/env python3
"""
查询王码网站的汉字拆解（五笔86/98/新世纪、数字王码等）。

用法示例：
  python3 wubi_query.py 测
  python3 wubi_query.py 汉 --max-retry 8

依赖：requests、Pillow、bs4 已在项目中使用；复用 captcha_ocr_test.py 里的验证码识别。
"""

import argparse
import io
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urljoin
import time

import requests
from bs4 import BeautifulSoup
from PIL import Image

from cnn.captcha_ocr_test import fetch_captcha
from cnn_inference import CNNInference

WMHZ1_URL = "http://www.wangma.com.cn/query/wmhz1.asp"
WMHZ2_URL = "http://www.wangma.com.cn/query/wmhz2.asp"
# 图片路径相对 wmhz2.asp 所在目录
BASE_URL = WMHZ2_URL


def parse_codes(html: str) -> dict:
    """从返回的 HTML 文本中提取编码字段。"""
    soup = BeautifulSoup(html, "html.parser")
    out: dict = {}
    for td in soup.find_all("td"):
        label = td.get_text(strip=True)
        if not label:
            continue
        val_td = td.find_next("td")
        if val_td is None:
            continue
        val = val_td.get_text(strip=True)
        imgs = []
        for img in val_td.find_all("img"):
            src = img.get("src", "").replace("\\", "/")
            if not src:
                continue
            imgs.append(urljoin(BASE_URL, src.lstrip("/")))
        if not val:
            continue
        if "数字王码" in label and "5键" in label:
            out.setdefault("num5", val)
        elif "数字王码" in label and "6键" in label:
            out.setdefault("num6", val)
            if imgs:
                out.setdefault("num6_components", imgs)
        elif "数字王码" in label and "9键" in label:
            out.setdefault("num9", val)
            if imgs:
                out.setdefault("num9_components", imgs)
        elif "王码五笔字型" in label and "86" in label:
            out.setdefault("wb86", val)
            if imgs:
                out.setdefault("wb86_components", imgs)
        elif "王码五笔字型" in label and "98" in label:
            out.setdefault("wb98", val)
            if imgs:
                out.setdefault("wb98_components", imgs)
        elif "王码五笔字型" in label and "新世纪" in label:
            out.setdefault("wb_xsj", val)
            if imgs:
                out.setdefault("wb_xsj_components", imgs)
        elif "笔画序列" in label:
            out.setdefault("strokes", val)
    return out


def download_components(codes: dict, outdir: Path) -> dict:
    """下载拆解图片到本地目录，返回 key -> 本地路径列表。"""
    outdir.mkdir(parents=True, exist_ok=True)
    mapping = {}
    for key in [
        "num6_components",
        "num9_components",
        "wb86_components",
        "wb98_components",
        "wb_xsj_components",
    ]:
        urls = codes.get(key) or []
        paths = []
        for url in urls:
            filename = url.split("/")[-1]
            dest = outdir / filename
            if not dest.exists():
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
            paths.append(str(dest.resolve()))
        if paths:
            mapping[key] = paths
    return mapping


def query_char(ch: str, max_retry: int = 5, predictor: Optional[CNNInference] = None) -> dict:
    if predictor is None:
        predictor = CNNInference(model_path="captcha_cnn.pth")

    last_html = ""
    for attempt in range(1, max_retry + 1):
        sess = requests.Session()
        sess.get(WMHZ1_URL, timeout=10)

        cap_bytes = fetch_captcha(sess)
        
        # Save captcha image for debugging
        timestamp = int(time.time() * 1000)
        debug_img_path = f"captcha_{timestamp}.jpg"
        with open(debug_img_path, "wb") as f:
            f.write(cap_bytes)
        print(f"[DEBUG] Captcha image saved to: {debug_img_path}", file=sys.stderr)

        code, conf = predictor.predict(Path(debug_img_path))
        # 4) 打印识别结果
        print(f"[DEBUG] Recognized code: {code} (conf: {conf:.2f})", file=sys.stderr)

        payload = {"query_hz": ch, "yanzhengma": code, "ok": "查询"}
        body = urlencode(payload, encoding="gb2312").encode("gb2312")
        headers = {"Referer": WMHZ1_URL, "Content-Type": "application/x-www-form-urlencoded"}
        resp = sess.post(WMHZ2_URL, data=body, headers=headers, timeout=10)
        html = resp.content.decode("gb2312", errors="replace")
        last_html = html

        if "验证码错误" in html:
            continue
        if "指定汉字错误" in html:
            raise ValueError(f"指定汉字错误：{ch}")

        codes = parse_codes(html)
        if codes:
            return codes
    raise RuntimeError("查询失败，可能验证码未通过或页面结构变化。最后一次响应片段:\n" + last_html[:400])


def main():
    ap = argparse.ArgumentParser(description="查询王码五笔/数字王码编码")
    ap.add_argument("char", help="要查询的单个汉字")
    ap.add_argument("--max-retry", type=int, default=5, help="验证码失败时的最大重试次数")
    ap.add_argument("--download-imgs", type=Path, help="将拆解图片下载到此目录，并输出本地路径")
    args = ap.parse_args()

    if len(args.char) != 1:
        raise SystemExit("请输入单个汉字进行查询")

    predictor = CNNInference(model_path="captcha_cnn.pth")
    codes = query_char(args.char, max_retry=args.max_retry, predictor=predictor)

    print(f"{args.char} 的编码：")
    print(f"  王码五笔86：{codes.get('wb86', '-')}")
    print(f"  王码五笔98：{codes.get('wb98', '-')}")
    print(f"  王码五笔新世纪：{codes.get('wb_xsj', '-')}")
    print(f"  数字王码5键：{codes.get('num5', '-')}")
    print(f"  数字王码6键：{codes.get('num6', '-')}")
    print(f"  数字王码9键：{codes.get('num9', '-')}")
    print(f"  笔画序列：{codes.get('strokes', '-')}")

    # 拆分部件的图片路径（站点上的 BMP），方便上层按需下载或展示。
    def fmt_imgs(key: str) -> str:
        imgs = codes.get(key)
        return " ".join(imgs) if imgs else "-"

    print(f"  数王6键拆解：{fmt_imgs('num6_components')}")
    print(f"  数王9键拆解：{fmt_imgs('num9_components')}")
    print(f"  五笔86拆解：{fmt_imgs('wb86_components')}")
    print(f"  五笔98拆解：{fmt_imgs('wb98_components')}")
    print(f"  五笔新世纪拆解：{fmt_imgs('wb_xsj_components')}")

    if args.download_imgs:
        local = download_components(codes, args.download_imgs)
        if local:
            print("  本地拆解图片：")
            for k, paths in local.items():
                print(f"    {k}: {' '.join(paths)}")


if __name__ == "__main__":
    main()
