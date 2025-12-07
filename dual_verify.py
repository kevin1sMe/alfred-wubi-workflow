#!/usr/bin/env python3
"""
双模型交叉验证自动标注工具

结合模板匹配和 EasyOCR 两种方法：
- 当两个模型结果一致时，自动标注（高置信度）
- 当两个模型结果不一致时，标记为需要人工复核（低置信度）

这样可以大幅减少需要人工审核的数量。

用法：
  # 在 macOS 上运行（需要先安装 easyocr）
  python3 dual_verify.py test_captchas/*.bmp
  
  # 试运行模式
  python3 dual_verify.py test_captchas/*.bmp --dry-run
  
  # 设置置信度策略
  python3 dual_verify.py test_captchas/*.bmp --strategy strict
"""

import argparse
import io
from pathlib import Path
from typing import List, Tuple, Optional

from PIL import Image

from captcha_ocr_test import CaptchaSolver

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False


def preprocess_for_easyocr(image_path: Path) -> Image.Image:
    """预处理图片以提高 EasyOCR 准确率"""
    im = Image.open(image_path)
    
    # 放大图片
    scale = 8
    new_size = (im.width * scale, im.height * scale)
    im = im.resize(new_size, Image.NEAREST)
    
    # 转换为灰度图
    im = im.convert('L')
    
    # 自适应阈值二值化
    pixels = list(im.getdata())
    threshold = sum(pixels) // len(pixels)
    im = im.point(lambda p: 255 if p > threshold else 0, mode='1')
    
    # 添加边距
    from PIL import ImageOps
    im = ImageOps.expand(im, border=10, fill=255)
    
    return im


def recognize_with_template(image_path: Path, solver: CaptchaSolver) -> Tuple[str, float]:
    """使用模板匹配识别"""
    try:
        im = Image.open(image_path)
        result = solver.solve(im)
        # 模板匹配没有置信度，根据结果长度给一个估计值
        confidence = 0.8 if len(result) == 4 else 0.0
        return result, confidence
    except Exception as e:
        return "", 0.0


def recognize_with_easyocr(image_path: Path, reader) -> Tuple[str, float]:
    """使用 EasyOCR 识别"""
    try:
        im = preprocess_for_easyocr(image_path)
        
        # 保存临时文件（EasyOCR 需要文件路径）
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            im.save(tmp.name)
            tmp_path = tmp.name
        
        # 识别
        results = reader.readtext(tmp_path, allowlist='0123456789', detail=1)
        
        # 清理临时文件
        Path(tmp_path).unlink()
        
        if not results:
            return "", 0.0
        
        # 合并所有识别结果
        text = "".join([result[1] for result in results])
        confidences = [result[2] for result in results]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        # 只保留数字
        import re
        text = re.sub(r'[^0-9]', '', text)
        
        return text, avg_confidence
    except Exception as e:
        return "", 0.0


def dual_verify_label(
    paths: List[Path],
    strategy: str = 'balanced',
    dry_run: bool = False
) -> dict:
    """
    双模型交叉验证标注
    
    Args:
        paths: 图片路径列表
        strategy: 策略
            - 'strict': 只有两个模型完全一致才自动标注
            - 'balanced': 两个模型一致或其中一个高置信度时自动标注
            - 'lenient': 优先使用模板匹配结果
        dry_run: 试运行模式
    
    Returns:
        统计信息字典
    """
    if not EASYOCR_AVAILABLE:
        raise RuntimeError("EasyOCR 未安装，请运行: pip install easyocr")
    
    # 初始化识别器
    print("初始化模板匹配识别器...")
    template_solver = CaptchaSolver.from_dir()
    
    print("初始化 EasyOCR 识别器（首次运行会下载模型）...")
    easyocr_reader = easyocr.Reader(['en'], gpu=False)
    
    stats = {
        'total': 0,
        'both_agree': 0,        # 两个模型一致
        'both_disagree': 0,     # 两个模型不一致
        'template_only': 0,     # 只有模板识别成功
        'easyocr_only': 0,      # 只有 EasyOCR 识别成功
        'both_failed': 0,       # 两个都失败
        'auto_labeled': 0,      # 自动标注
        'need_review': 0,       # 需要人工复核
    }
    
    auto_labeled_cases = []
    need_review_cases = []
    
    for path in paths:
        stats['total'] += 1
        
        print(f"\n处理: {path.name}")
        
        # 使用两个模型识别
        template_result, template_conf = recognize_with_template(path, template_solver)
        easyocr_result, easyocr_conf = recognize_with_easyocr(path, easyocr_reader)
        
        print(f"  模板匹配: {template_result or '(失败)'} (置信度: {template_conf:.2%})")
        print(f"  EasyOCR:  {easyocr_result or '(失败)'} (置信度: {easyocr_conf:.2%})")
        
        # 判断是否都是有效结果（4位数字）
        template_valid = len(template_result) == 4
        easyocr_valid = len(easyocr_result) == 4
        
        # 决策逻辑
        should_auto_label = False
        final_result = ""
        reason = ""
        
        if template_valid and easyocr_valid:
            if template_result == easyocr_result:
                # 两个模型一致
                stats['both_agree'] += 1
                should_auto_label = True
                final_result = template_result
                reason = "两个模型一致"
            else:
                # 两个模型不一致
                stats['both_disagree'] += 1
                if strategy == 'strict':
                    should_auto_label = False
                    reason = "两个模型不一致，需要人工复核"
                elif strategy == 'balanced':
                    # 选择置信度更高的
                    if template_conf > 0.9 or easyocr_conf > 0.9:
                        should_auto_label = True
                        final_result = template_result if template_conf > easyocr_conf else easyocr_result
                        reason = f"选择高置信度结果 ({template_conf:.2%} vs {easyocr_conf:.2%})"
                    else:
                        should_auto_label = False
                        reason = f"两个模型不一致且置信度都不高，需要人工复核"
                else:  # lenient
                    should_auto_label = True
                    final_result = template_result
                    reason = "优先使用模板匹配结果"
        elif template_valid:
            stats['template_only'] += 1
            if strategy != 'strict':
                should_auto_label = True
                final_result = template_result
                reason = "只有模板匹配成功"
            else:
                should_auto_label = False
                reason = "EasyOCR 失败，需要人工复核"
        elif easyocr_valid:
            stats['easyocr_only'] += 1
            if strategy == 'lenient':
                should_auto_label = True
                final_result = easyocr_result
                reason = "只有 EasyOCR 成功"
            else:
                should_auto_label = False
                reason = "模板匹配失败，需要人工复核"
        else:
            stats['both_failed'] += 1
            should_auto_label = False
            reason = "两个模型都失败"
        
        # 执行标注或标记复核
        if should_auto_label:
            stats['auto_labeled'] += 1
            auto_labeled_cases.append((path.name, final_result, reason))
            
            # 重命名文件
            new_name = f"{path.stem}_{final_result}{path.suffix}"
            new_path = path.parent / new_name
            
            if new_path.exists() and new_path != path:
                print(f"  ⚠️  目标文件已存在: {new_name}")
            elif not dry_run and path != new_path:
                path.rename(new_path)
                print(f"  ✓ 自动标注: {new_name} ({reason})")
            else:
                print(f"  ✓ 自动标注: {final_result} ({reason}) [试运行]")
        else:
            stats['need_review'] += 1
            need_review_cases.append((path.name, template_result, easyocr_result, reason))
            print(f"  ⚠️  需要人工复核: {reason}")
    
    return {
        'stats': stats,
        'auto_labeled': auto_labeled_cases,
        'need_review': need_review_cases,
    }


def main():
    ap = argparse.ArgumentParser(description="双模型交叉验证自动标注")
    ap.add_argument('files', nargs='+', help='验证码图片文件')
    ap.add_argument('--strategy', choices=['strict', 'balanced', 'lenient'], 
                    default='balanced',
                    help='标注策略 (默认: balanced)')
    ap.add_argument('--dry-run', action='store_true',
                    help='试运行模式，不实际重命名文件')
    args = ap.parse_args()
    
    if not EASYOCR_AVAILABLE:
        print("错误：EasyOCR 未安装")
        print("请在 macOS 上运行: pip install easyocr")
        return 1
    
    paths = [Path(p) for p in args.files]
    
    print(f"双模型交叉验证标注")
    print(f"策略: {args.strategy}")
    print(f"处理 {len(paths)} 个文件\n")
    
    result = dual_verify_label(paths, strategy=args.strategy, dry_run=args.dry_run)
    
    stats = result['stats']
    
    print("\n" + "=" * 70)
    print("统计信息:")
    print(f"  总计: {stats['total']}")
    print(f"  两个模型一致: {stats['both_agree']}")
    print(f"  两个模型不一致: {stats['both_disagree']}")
    print(f"  只有模板成功: {stats['template_only']}")
    print(f"  只有 EasyOCR 成功: {stats['easyocr_only']}")
    print(f"  两个都失败: {stats['both_failed']}")
    print(f"\n  ✓ 自动标注: {stats['auto_labeled']}")
    print(f"  ⚠️  需要人工复核: {stats['need_review']}")
    
    if result['need_review']:
        print(f"\n需要人工复核的文件：")
        for name, template_res, easyocr_res, reason in result['need_review']:
            print(f"  {name}")
            print(f"    模板: {template_res or '(失败)'}, EasyOCR: {easyocr_res or '(失败)'}")
            print(f"    原因: {reason}")
        
        print(f"\n建议：")
        print(f"  python3 captcha_ocr_test.py label \\")
        for name, _, _, _ in result['need_review'][:5]:  # 只显示前5个
            print(f"    {name} \\")
        if len(result['need_review']) > 5:
            print(f"    ... (还有 {len(result['need_review']) - 5} 个)")
    
    reduction = (1 - stats['need_review'] / stats['total']) * 100 if stats['total'] > 0 else 0
    print(f"\n人工审核工作量减少: {reduction:.1f}%")
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    exit(main())
