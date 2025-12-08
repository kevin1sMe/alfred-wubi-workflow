#!/usr/bin/env python3
"""
自动标注验证码工具 - 使用 Tesseract OCR 或 EasyOCR

用法示例：
  # 使用 Tesseract 自动标注
  python3 auto_label.py captchas/*.bmp

  # 使用 EasyOCR（需要先安装 easyocr）
  python3 auto_label.py captchas/*.bmp --method easyocr

  # 验证模式：对比外部 OCR 和模板识别结果
  python3 auto_label.py captchas/*.bmp --verify

  # 设置置信度阈值
  python3 auto_label.py captchas/*.bmp --confidence 0.9
"""

import argparse
import re
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False


def preprocess_for_ocr(image_path: Path) -> Image.Image:
    """预处理图片以提高 OCR 准确率"""
    im = Image.open(image_path)
    
    # 放大图片（Tesseract 对小图片识别效果不好）
    # 原图是 40x11，放大 8 倍到 320x88
    scale = 8
    new_size = (im.width * scale, im.height * scale)
    im = im.resize(new_size, Image.NEAREST)
    
    # 转换为灰度图
    im = im.convert('L')
    
    # 使用自适应阈值进行二值化
    # 先获取像素数据
    pixels = list(im.getdata())
    # 计算阈值（使用 Otsu 方法的简化版本）
    threshold = sum(pixels) // len(pixels)
    
    # 二值化
    im = im.point(lambda p: 255 if p > threshold else 0, mode='1')
    
    # 添加边距（Tesseract 在有边距时效果更好）
    from PIL import ImageOps
    im = ImageOps.expand(im, border=10, fill=255)
    
    return im


def auto_label_tesseract(image_path: Path) -> Tuple[str, float]:
    """
    使用 Tesseract OCR 识别验证码
    返回：(识别结果, 置信度)
    """
    if not TESSERACT_AVAILABLE:
        raise RuntimeError("pytesseract 未安装，请运行: pip install pytesseract")
    
    im = preprocess_for_ocr(image_path)
    
    # 配置 Tesseract：只识别数字，使用单行模式
    # --oem 3: 使用默认 OCR 引擎
    # --psm 7: 单行文本模式
    # tessedit_char_whitelist: 只识别数字
    custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'
    
    try:
        # 获取详细结果（包含置信度）
        data = pytesseract.image_to_data(im, config=custom_config, output_type=pytesseract.Output.DICT)
        
        # 提取文本和置信度
        text = ""
        confidences = []
        for i, conf in enumerate(data['conf']):
            if int(conf) > 0:  # 过滤掉无效结果
                text += data['text'][i]
                confidences.append(int(conf))
        
        # 清理结果：只保留数字
        text = re.sub(r'[^0-9]', '', text)
        
        # 计算平均置信度
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        return text, avg_confidence / 100.0  # 转换为 0-1 范围
    except Exception as e:
        # 如果出错，返回空结果
        return "", 0.0


def auto_label_easyocr(image_path: Path) -> Tuple[str, float]:
    """
    使用 EasyOCR 识别验证码
    返回：(识别结果, 置信度)
    """
    if not EASYOCR_AVAILABLE:
        raise RuntimeError("easyocr 未安装，请运行: pip install easyocr")
    
    # Initialize EasyOCR reader (only recognize English numbers)
    reader = easyocr.Reader(['en'], gpu=False)
    import numpy as np
    
    im = preprocess_for_ocr(image_path)
    # EasyOCR expects a numpy array (preferably RGB for consistent results)
    im_np = np.array(im.convert('RGB'))
    
    # Recognize
    results = reader.readtext(im_np, allowlist='0123456789', detail=1)
    
    if not results:
        return "", 0.0
    
    # 合并所有识别结果
    text = "".join([result[1] for result in results])
    confidences = [result[2] for result in results]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    
    # 清理结果
    text = re.sub(r'[^0-9]', '', text)
    
    return text, avg_confidence


def extract_label(path: Path) -> str:
    """从文件名中提取标签"""
    matches = re.findall(r'(\d{4})', path.stem)
    return matches[-1] if matches else ""


def batch_auto_label(
    paths: List[Path],
    method: str = 'tesseract',
    confidence_threshold: float = 0.0,
    verify_mode: bool = False,
    dry_run: bool = False
) -> dict:
    """
    批量自动标注验证码
    
    Args:
        paths: 图片路径列表
        method: OCR 方法 ('tesseract' 或 'easyocr')
        confidence_threshold: 置信度阈值，低于此值的结果会被标记
        verify_mode: 验证模式，对比 OCR 结果和文件名中的标签
        dry_run: 试运行模式，不实际重命名文件
    
    Returns:
        统计信息字典
    """
    ocr_func = auto_label_tesseract if method == 'tesseract' else auto_label_easyocr
    
    stats = {
        'total': 0,
        'success': 0,
        'low_confidence': 0,
        'invalid_length': 0,
        'renamed': 0,
        'verify_match': 0,
        'verify_mismatch': 0,
    }
    
    low_conf_cases = []
    verify_mismatches = []
    
    for path in paths:
        stats['total'] += 1
        
        try:
            result, confidence = ocr_func(path)
        except Exception as e:
            print(f"❌ {path.name}: 识别失败 - {e}")
            continue
        
        # 验证模式
        if verify_mode:
            existing_label = extract_label(path)
            if existing_label:
                if result == existing_label:
                    stats['verify_match'] += 1
                    print(f"✓ {path.name}: {result} (置信度: {confidence:.2%})")
                else:
                    stats['verify_mismatch'] += 1
                    verify_mismatches.append((path.name, existing_label, result, confidence))
                    print(f"✗ {path.name}: 标签={existing_label}, OCR={result} (置信度: {confidence:.2%})")
            continue
        
        # 检查结果长度
        if len(result) != 4:
            stats['invalid_length'] += 1
            print(f"⚠️  {path.name}: 识别结果长度不是4位 - '{result}' (置信度: {confidence:.2%})")
            continue
        
        stats['success'] += 1
        
        # 检查置信度
        if confidence < confidence_threshold:
            stats['low_confidence'] += 1
            low_conf_cases.append((path.name, result, confidence))
            print(f"⚠️  {path.name}: {result} (低置信度: {confidence:.2%})")
            continue
        
        # 重命名文件
        new_name = f"{path.stem}_{result}{path.suffix}"
        new_path = path.parent / new_name
        
        if new_path.exists() and new_path != path:
            print(f"⚠️  {path.name}: 目标文件已存在 - {new_name}")
            continue
        
        if not dry_run and path != new_path:
            path.rename(new_path)
            stats['renamed'] += 1
            print(f"✓ {path.name} -> {new_name} (置信度: {confidence:.2%})")
        else:
            print(f"✓ {path.name}: {result} (置信度: {confidence:.2%})")
    
    return {
        'stats': stats,
        'low_confidence_cases': low_conf_cases,
        'verify_mismatches': verify_mismatches,
    }


def main():
    ap = argparse.ArgumentParser(description="自动标注验证码")
    ap.add_argument('files', nargs='+', help='验证码图片文件')
    ap.add_argument('--method', choices=['tesseract', 'easyocr'], default='tesseract',
                    help='OCR 方法 (默认: tesseract)')
    ap.add_argument('--confidence', type=float, default=0.0,
                    help='置信度阈值，低于此值的结果会被标记 (0.0-1.0)')
    ap.add_argument('--verify', action='store_true',
                    help='验证模式：对比 OCR 结果和文件名中的标签')
    ap.add_argument('--dry-run', action='store_true',
                    help='试运行模式，不实际重命名文件')
    args = ap.parse_args()
    
    # 检查依赖
    if args.method == 'tesseract' and not TESSERACT_AVAILABLE:
        print("错误：pytesseract 未安装")
        print("安装方法：")
        print("  1. 安装 Tesseract: sudo apt-get install tesseract-ocr")
        print("  2. 安装 Python 库: pip install pytesseract")
        return 1
    
    if args.method == 'easyocr' and not EASYOCR_AVAILABLE:
        print("错误：easyocr 未安装")
        print("安装方法：pip install easyocr")
        return 1
    
    paths = [Path(p) for p in args.files]
    
    print(f"使用 {args.method.upper()} 进行{'验证' if args.verify else '自动标注'}...")
    print(f"处理 {len(paths)} 个文件\n")
    
    result = batch_auto_label(
        paths,
        method=args.method,
        confidence_threshold=args.confidence,
        verify_mode=args.verify,
        dry_run=args.dry_run
    )
    
    stats = result['stats']
    
    print("\n" + "=" * 60)
    print("统计信息:")
    print(f"  总计: {stats['total']}")
    
    if args.verify:
        print(f"  匹配: {stats['verify_match']}")
        print(f"  不匹配: {stats['verify_mismatch']}")
        
        if result['verify_mismatches']:
            print("\n不匹配的案例：")
            for name, label, ocr_result, conf in result['verify_mismatches']:
                print(f"  {name}: 标签={label}, OCR={ocr_result} (置信度: {conf:.2%})")
    else:
        print(f"  成功识别: {stats['success']}")
        print(f"  长度错误: {stats['invalid_length']}")
        print(f"  低置信度: {stats['low_confidence']}")
        print(f"  已重命名: {stats['renamed']}")
        
        if result['low_confidence_cases']:
            print(f"\n低置信度案例（< {args.confidence:.0%}）：")
            for name, text, conf in result['low_confidence_cases']:
                print(f"  {name}: {text} (置信度: {conf:.2%})")
    
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    exit(main())
