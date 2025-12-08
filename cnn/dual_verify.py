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

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

def preprocess_for_tesseract(image_path: Path) -> Image.Image:
    """Preprocess for Tesseract (similar to existing auto_label.py logic)"""
    im = Image.open(image_path)
    # Tesseract 最佳实践：
    # 1. 不要过度放大 (Scale 2 优于 Scale 8)
    # 2. 保留灰度细节，不要强制二值化 (除非非常干净)
    # 3. 适当的白边 (Padding)
    scale = 2
    new_size = (im.width * scale, im.height * scale)
    im = im.resize(new_size, Image.NEAREST)
    im = im.convert('L')
    
    # 移除强制二值化，让 Tesseract 自己处理
    # pixels = list(im.getdata())
    # threshold = sum(pixels) // len(pixels)
    # im = im.point(lambda p: 255 if p > threshold else 0, mode='1')
    
    from PIL import ImageOps
    im = ImageOps.expand(im, border=10, fill=255)
    return im

def recognize_with_tesseract(image_path: Path) -> Tuple[str, float]:
    """Use Tesseract"""
    if not TESSERACT_AVAILABLE:
        return "", 0.0
    try:
        im = preprocess_for_tesseract(image_path)
        custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'
        data = pytesseract.image_to_data(im, config=custom_config, output_type=pytesseract.Output.DICT)
        text = ""
        confidences = []
        for i, conf in enumerate(data['conf']):
            if int(conf) > 0:
                text += data['text'][i]
                confidences.append(int(conf))
        import re
        text = re.sub(r'[^0-9]', '', text)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return text, avg_confidence / 100.0
    except Exception as e:
        print(f"DEBUG: Tesseract error: {e}")
        return "", 0.0

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
    
    return im.convert('RGB')


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
        print(f"DEBUG: EasyOCR error: {e}")
        return "", 0.0


def extract_label(path: Path) -> str:
    """从文件名中提取标签"""
    import re
    matches = re.findall(r'(\d{4})', path.stem)
    return matches[-1] if matches else ""


try:
    from cnn_inference import CNNInference
    CNN_AVAILABLE = True
except ImportError:
    CNN_AVAILABLE = False
    print("Warning: cnn_inference.py not found, skipping custom model.")

def dual_verify_label(
    paths: List[Path],
    strategy: str = 'balanced',
    dry_run: bool = False,
    force_rename: bool = False
) -> dict:
    """
    多模型交叉验证标注 (Template, EasyOCR, Tesseract, Custom CNN)
    """
    if not EASYOCR_AVAILABLE:
        raise RuntimeError("EasyOCR 未安装，请运行: pip install easyocr")
    
    # 初始化识别器
    print("初始化模板匹配识别器...")
    template_solver = CaptchaSolver.from_dir()
    
    print("初始化 EasyOCR 识别器（首次运行会下载模型）...")
    easyocr_reader = easyocr.Reader(['en'], gpu=False)
    
    cnn_model = None
    if CNN_AVAILABLE:
        try:
            print("初始化自定义 CNN 模型...")
            cnn_model = CNNInference("captcha_cnn.pth")
        except Exception as e:
            print(f"加载 CNN 模型失败: {e}")
            cnn_model = None
    
    stats = {
        'total': 0,
        'both_agree': 0,        # Template & EasyOCR 一致
        'both_disagree': 0,
        'template_only': 0,
        'easyocr_only': 0,
        'both_failed': 0,
        'auto_labeled': 0,
        'need_review': 0,
        'label_match': 0,       # 现有标签与最终决定一致
        'label_mismatch': 0,
        'tesseract_agree': 0,
        'cnn_agree': 0,         # Custom CNN 与最终决定一致
    }
    
    auto_labeled_cases = []
    need_review_cases = []
    suspicious_cases = []
    details = []

    for path in paths:
        stats['total'] += 1
        
        print(f"\n处理: {path.name}")
        existing_label = extract_label(path)
        
        # 使用四个模型识别
        template_result, template_conf = recognize_with_template(path, template_solver)
        easyocr_result, easyocr_conf = recognize_with_easyocr(path, easyocr_reader)
        tesseract_result, tesseract_conf = recognize_with_tesseract(path)
        
        cnn_result, cnn_conf = ("", 0.0)
        if cnn_model:
            cnn_result, cnn_conf = cnn_model.predict(path)
        
        print(f"  现有标签: {existing_label or '(无)'}")
        print(f"  模板匹配: {template_result or '(失败)'} (置信度: {template_conf:.2%})")
        print(f"  EasyOCR:  {easyocr_result or '(失败)'} (置信度: {easyocr_conf:.2%})")
        print(f"  Tesseract:{tesseract_result or '(失败)'} (置信度: {tesseract_conf:.2%})")
        print(f"  CustomCNN:{cnn_result or '(失败)'} (置信度: {cnn_conf:.2%})")
        
        # ... logic continues ...
        
        # ... logic continues ...
        
        # ... we need to map back the decision logic into the loop properly, or careful replacement.
        # Since I'm replacing the top of the function, I need to ensure the rest matches.
        # It's better to replace just the initialization block and the recognition block?
        # The tool `replace_file_content` replaces a contiguous block.
        # I will replace from imports down to valid checks.

        template_valid = len(template_result) == 4
        easyocr_valid = len(easyocr_result) == 4
        
        # 决策逻辑 (主要基于 Template 和 EasyOCR)
        should_auto_label = False
        final_result = ""
        reason = ""
        status_code = "" # Auto, Match, Suspicious, Review
        
        if template_valid and easyocr_valid:
            if template_result == easyocr_result:
                # 两个模型一致
                stats['both_agree'] += 1
                should_auto_label = True
                final_result = template_result
                reason = "两个模型一致"
                status_code = "Match"
            else:
                # 两个模型不一致
                stats['both_disagree'] += 1
                if strategy == 'strict':
                    should_auto_label = False
                    reason = "两个模型不一致，需要人工复核"
                    status_code = "Review"
                elif strategy == 'balanced':
                    # 选择置信度更高的
                    if template_conf > 0.9 or easyocr_conf > 0.9:
                        should_auto_label = True
                        final_result = template_result if template_conf > easyocr_conf else easyocr_result
                        reason = f"选择高置信度结果 ({template_conf:.2%} vs {easyocr_conf:.2%})"
                        status_code = "Auto"
                    else:
                        should_auto_label = False
                        reason = f"两个模型不一致且置信度都不高，需要人工复核"
                        status_code = "Review"
                else:  # lenient
                    should_auto_label = True
                    final_result = template_result
                    reason = "优先使用模板匹配结果"
                    status_code = "Auto"
        elif template_valid:
            stats['template_only'] += 1
            if strategy != 'strict':
                should_auto_label = True
                final_result = template_result
                reason = "只有模板匹配成功"
                status_code = "Auto"
            else:
                should_auto_label = False
                reason = "EasyOCR 失败，需要人工复核"
                status_code = "Review"
        elif easyocr_valid:
            stats['easyocr_only'] += 1
            if strategy == 'lenient':
                should_auto_label = True
                final_result = easyocr_result
                reason = "只有 EasyOCR 成功"
                status_code = "Auto"
            else:
                should_auto_label = False
                reason = "模板匹配失败，需要人工复核"
                status_code = "Review"
        else:
            stats['both_failed'] += 1
            should_auto_label = False
            reason = "两个模型都失败"
            status_code = "Fail"
        
        # Tesseract 统计
        if final_result and final_result == tesseract_result:
            stats['tesseract_agree'] += 1
            
        if final_result and final_result == cnn_result:
            stats['cnn_agree'] += 1

        # 如果决定了标签，与现有标签对比
        if should_auto_label and existing_label:
            if final_result == existing_label:
                stats['label_match'] += 1
                print(f"  ✓ 标签验证通过")
                status_code = "Match"
            else:
                stats['label_mismatch'] += 1
                suspicious_cases.append((path.name, existing_label, final_result, reason))
                print(f"  ❌ 标签不匹配! 原标: {existing_label} -> 预测: {final_result}")
                
                # 默认暂停重命名，除非 force_rename
                if not force_rename:
                    if not dry_run: 
                         should_auto_label = False 
                         reason = f"疑似标错: 原={existing_label}, 新={final_result}"
                    status_code = "Suspicious"
                else:
                    status_code = "Corrected" # Newly labeled
                    reason += " [强制更名]"

        # 收集详细信息
        details.append({
            'name': path.name,
            'label': existing_label,
            'template': template_result,
            'easyocr': easyocr_result,
            'tesseract': tesseract_result,
            'cnn': cnn_result,
            'suggestion': final_result if should_auto_label or status_code == "Suspicious" else "",
            'status': status_code,
            'reason': reason
        })

        # 执行标注或标记复核
        if should_auto_label:
            stats['auto_labeled'] += 1
            auto_labeled_cases.append((path.name, final_result, reason))
            
            # 重命名文件
            new_name = f"{path.stem.split('_')[0]}_{final_result}{path.suffix}" # 保持前缀
            if existing_label and existing_label in path.stem:
                 # 替换掉原来的标签
                 new_name = path.name.replace(existing_label, final_result)
            else:
                 new_name = f"{path.stem}_{final_result}{path.suffix}"
                 
            new_path = path.parent / new_name
            
            if new_path.exists() and new_path != path:
                print(f"  ⚠️  目标文件已存在: {new_name}")
            elif not dry_run and path != new_path:
                path.rename(new_path)
                print(f"  ✓ 自动矫正/标注: {new_name} ({reason})")
            else:
                print(f"  ✓ 建议标注: {final_result} ({reason}) [试运行]")
        else:
            stats['need_review'] += 1
            need_review_cases.append((path.name, template_result, easyocr_result, reason))
            print(f"  ⚠️  需要人工复核: {reason}")
    
    return {
        'stats': stats,
        'auto_labeled': auto_labeled_cases,
        'need_review': need_review_cases,
        'suspicious': suspicious_cases,
        'details': details
    }


def main():
    ap = argparse.ArgumentParser(description="双模型交叉验证 / 纠错工具")
    ap.add_argument('files', nargs='+', help='验证码图片文件')
    ap.add_argument('--strategy', choices=['strict', 'balanced', 'lenient'], 
                    default='balanced',
                    help='标注策略 (默认: balanced)')
    ap.add_argument('--dry-run', action='store_true',
                    help='试运行模式，不实际重命名文件')
    ap.add_argument('--report', type=str, help='Save comparison report to file (e.g. report.md)')
    ap.add_argument('--force-rename', action='store_true',
                    help='强制重命名，即使原标签与预测不一致（用于批量修正或初次标注）')
    args = ap.parse_args()
    
    if not EASYOCR_AVAILABLE:
        print("错误：EasyOCR 未安装")
        print("请在 macOS 上运行: pip install easyocr")
        return 1
    
    paths = [Path(p) for p in args.files]
    
    print(f"多模型交叉验证 (含 Tesseract)")
    print(f"策略: {args.strategy}")
    print(f"模式: {'试运行' if args.dry_run else '执行'}")
    print(f"强制重命名: {'是' if args.force_rename else '否'}")
    print(f"处理 {len(paths)} 个文件\n")
    
    # We need to modify dual_verify_label to pass back the full details list, or we move the printing logic here?
    # To avoid changing too much logic, let's just make dual_verify_label return a 'details' list.
    # But since I can't easily modify the function signature and body in one go with replace_file_content without context of the whole file...
    # I will rely on the fact that I can edit `dual_verify_label` to collect details.
    
    # Let's actually rewrite dual_verify_label's return to include 'all_details'.
    # But wait, I'm in 'main'. I need to edit 'dual_verify_label' first or assumes it returns what I need.
    # The previous edit attempts to add reporting in main but realized it didn't have the data.
    # So I will rewrite `dual_verify_label` to return `all_details` list.
    
    result = dual_verify_label(paths, strategy=args.strategy, dry_run=args.dry_run, force_rename=args.force_rename)
    stats = result['stats']

    # Generate Report if requested
    if args.report:
        with open(args.report, 'w') as f:
            f.write(f"# Captcha Recognition Report\n\n")
            f.write(f"Date: {import_datetime().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Strategy: {args.strategy}\n\n")
            f.write(f"## Statistics\n")
            f.write(f"- Total: {stats['total']}\n")
            
            # Calculate accuracy if labels exist
            total_with_labels = 0
            template_correct = 0
            easyocr_correct = 0
            tesseract_correct = 0
            cnn_correct = 0
            
            if 'details' in result:
                for item in result['details']:
                    if item['label']:
                        total_with_labels += 1
                        if item['template'] == item['label']:
                            template_correct += 1
                        if item['easyocr'] == item['label']:
                            easyocr_correct += 1
                        if item['tesseract'] == item['label']:
                            tesseract_correct += 1
                        if item.get('cnn') == item['label']:
                            cnn_correct += 1
            
            if total_with_labels > 0:
                f.write(f"### Accuracy (Ground Truth: Original Label, N={total_with_labels})\n")
                f.write(f"- **Template Matching**: {template_correct}/{total_with_labels} ({template_correct/total_with_labels:.1%})\n")
                f.write(f"- **EasyOCR**: {easyocr_correct}/{total_with_labels} ({easyocr_correct/total_with_labels:.1%})\n")
                f.write(f"- **Tesseract**: {tesseract_correct}/{total_with_labels} ({tesseract_correct/total_with_labels:.1%})\n")
                f.write(f"- **Custom CNN**: {cnn_correct}/{total_with_labels} ({cnn_correct/total_with_labels:.1%})\n\n")
            
            f.write(f"### Other Metrics\n")
            f.write(f"- Matches (Template == EasyOCR): {stats['both_agree']}\n")
            f.write(f"- Tesseract Agreement: {stats['tesseract_agree']}\n")
            f.write(f"- Custom CNN Agreement: {stats['cnn_agree']}\n")
            f.write(f"- Label Matches (Prediction == Label): {stats['label_match']}\n")
            f.write(f"- Mismatches (Prediction != Label): {stats['label_mismatch']}\n\n")
            
            f.write(f"## Detailed Comparison\n\n")
            f.write(f"| File | Original | Template | EasyOCR | Tesseract | Custom CNN | Status |\n")
            f.write(f"|------|----------|----------|---------|-----------|------------|--------|\n")
            
            # The result dict MUST contain a 'details' key with list of dicts.
            if 'details' in result:
                for item in result['details']:
                    cnn_val = item.get('cnn', '')
                    
                    # Count how many other models agree with CNN
                    others = [item['template'], item['easyocr'], item['tesseract']]
                    match_count = 0
                    for other in others:
                        # Normalize 'failed' or empty to prevent matching empty strings
                        if other and other != "(失败)" and other == cnn_val:
                            match_count += 1
                    
                    if not cnn_val:
                         status_icon = "⚠️"
                         status_text = "CNN Failed"
                    elif match_count >= 2:
                         status_icon = "✅"
                         status_text = "Trusted"      # Agreed with >=2 others
                    elif match_count == 1:
                         status_icon = "❓"
                         status_text = "Possible"     # Agreed with 1 other
                    else:
                         status_icon = "❌"
                         status_text = "Unique"       # Disagrees with all (Likely CNN is right & others wrong, based on user feedback)
                    
                    # Special case: If matches original label (if present)
                    if item['label'] and cnn_val == item['label']:
                         status_icon = "✅"
                         status_text = "Matches Label"

                    f.write(f"| {item['name']} | {item['label']} | {item['template']} | {item['easyocr']} | {item['tesseract']} | {cnn_val} | {status_icon} {status_text} |\n")
            else:
                f.write("\n_Details not available (script update needed)_\n")

    print("\n" + "=" * 70)
    print("统计信息:")
    print(f"  总计: {stats['total']}")
    print(f"  模型一致 (T=E): {stats['both_agree']}")
    print(f"  Tesseract 一致: {stats['tesseract_agree']}")
    print(f"  Custom CNN 一致: {stats['cnn_agree']}")
    print(f"  只有模板: {stats['template_only']}")
    print(f"  只有 EasyOCR: {stats['easyocr_only']}")
    print(f"  标签匹配: {stats['label_match']}")
    print(f"  疑似标错: {stats['label_mismatch']}  <-- 重点关注")
    
    # Reduced console output as requested, just summary + serious warnings
    # Maybe listing suspicious is still useful? User didn't ask to remove console output, only report.
    # Keep console output as is or simplify? "不要展示suggestion这一列" refers to report.
    # But logic for "Suspicious" in result['suspicious'] is based on OLD logic (dual verify).
    # Since we changed report perspective, the console "Suspicious" might be confusing if it differs.
    # But result['suspicious'] comes from `dual_verify_label` function which we haven't changed the core logic of.
    # We only changed report. Let's keep console as legacy/debug info.
    
    if result['suspicious']:
        print(f"\n🔥 疑似标错的案例 (建议检查):")
        for name, label, new_label, reason in result['suspicious']:
            print(f"  {name}: 原标={label} -> 建议={new_label} ({reason})")

    if result['need_review']:
        print(f"\n需要人工复核的文件 (模型不确定):")
        count = 0
        for name, template_res, easyocr_res, reason in result['need_review']:
             if count < 10:
                print(f"  {name}: T={template_res}, E={easyocr_res} ({reason})")
             count += 1
        if count > 10:
             print(f"  ... 还有 {count - 10} 个")

    if args.report:
        print(f"\n📄 报告已保存至: {args.report}")

    print("=" * 70)
    
    return 0

def import_datetime():
    from datetime import datetime
    return datetime.now()
    
    print("\n" + "=" * 70)
    print("统计信息:")
    print(f"  总计: {stats['total']}")
    print(f"  模型一致: {stats['both_agree']}")
    print(f"  只有模板: {stats['template_only']}")
    print(f"  只有 EasyOCR: {stats['easyocr_only']}")
    print(f"  标签匹配: {stats['label_match']}")
    print(f"  疑似标错: {stats['label_mismatch']}  <-- 重点关注")
    
    if result['suspicious']:
        print(f"\n🔥 疑似标错的案例 (建议检查):")
        for name, label, new_label, reason in result['suspicious']:
            print(f"  {name}: 原标={label} -> 建议={new_label} ({reason})")

    if result['need_review']:
        print(f"\n需要人工复核的文件 (模型不确定):")
        # 限制输出数量
        count = 0
        for name, template_res, easyocr_res, reason in result['need_review']:
             if count < 10:
                print(f"  {name}: T={template_res}, E={easyocr_res} ({reason})")
             count += 1
        if count > 10:
             print(f"  ... 还有 {count - 10} 个")

    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    exit(main())
