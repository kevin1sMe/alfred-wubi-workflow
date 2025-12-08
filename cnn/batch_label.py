#!/usr/bin/env python3
"""
使用现有模板识别器进行批量自动标注

这是最实用的方案：
1. 使用已有的高准确率模板匹配方法识别验证码
2. 自动重命名文件
3. 只需人工复核识别失败的案例

用法：
  python3 batch_label.py test_captchas/*.bmp
  python3 batch_label.py test_captchas/*.bmp --dry-run
"""

import argparse
import io
from pathlib import Path
from typing import List

from PIL import Image

from captcha_ocr_test import CaptchaSolver


def batch_label_with_template(
    paths: List[Path],
    dry_run: bool = False,
    solver: CaptchaSolver = None
) -> dict:
    """
    使用模板匹配批量标注验证码
    
    Args:
        paths: 图片路径列表
        dry_run: 试运行模式，不实际重命名
        solver: CaptchaSolver 实例，如果为 None 则自动创建
    
    Returns:
        统计信息字典
    """
    if solver is None:
        solver = CaptchaSolver.from_dir()
    
    stats = {
        'total': 0,
        'success': 0,
        'failed': 0,
        'renamed': 0,
        'skipped': 0,
    }
    
    failed_cases = []
    
    for path in paths:
        stats['total'] += 1
        
        try:
            # 使用模板匹配识别
            im = Image.open(path)
            result = solver.solve(im)
            
            if len(result) != 4:
                stats['failed'] += 1
                failed_cases.append((path.name, result, "长度不是4位"))
                print(f"❌ {path.name}: 识别失败 - '{result}' (长度: {len(result)})")
                continue
            
            stats['success'] += 1
            
            # 检查文件名是否已经包含标签
            if f"_{result}" in path.stem:
                stats['skipped'] += 1
                print(f"⏭️  {path.name}: 已标注 - {result}")
                continue
            
            # 重命名文件
            new_name = f"{path.stem}_{result}{path.suffix}"
            new_path = path.parent / new_name
            
            if new_path.exists() and new_path != path:
                stats['skipped'] += 1
                print(f"⚠️  {path.name}: 目标文件已存在 - {new_name}")
                continue
            
            if not dry_run and path != new_path:
                path.rename(new_path)
                stats['renamed'] += 1
                print(f"✓ {path.name} -> {new_name}")
            else:
                print(f"✓ {path.name}: {result} (试运行)")
                
        except Exception as e:
            stats['failed'] += 1
            failed_cases.append((path.name, "", str(e)))
            print(f"❌ {path.name}: 识别失败 - {e}")
    
    return {
        'stats': stats,
        'failed_cases': failed_cases,
    }


def main():
    ap = argparse.ArgumentParser(description="使用模板匹配批量自动标注验证码")
    ap.add_argument('files', nargs='+', help='验证码图片文件')
    ap.add_argument('--dry-run', action='store_true',
                    help='试运行模式，不实际重命名文件')
    args = ap.parse_args()
    
    paths = [Path(p) for p in args.files]
    
    print(f"使用模板匹配进行批量标注...")
    print(f"处理 {len(paths)} 个文件\n")
    
    solver = CaptchaSolver.from_dir()
    result = batch_label_with_template(paths, dry_run=args.dry_run, solver=solver)
    
    stats = result['stats']
    
    print("\n" + "=" * 60)
    print("统计信息:")
    print(f"  总计: {stats['total']}")
    print(f"  成功识别: {stats['success']}")
    print(f"  识别失败: {stats['failed']}")
    print(f"  已重命名: {stats['renamed']}")
    print(f"  跳过: {stats['skipped']}")
    
    if result['failed_cases']:
        print(f"\n失败案例（需要人工标注）：")
        for name, result_text, reason in result['failed_cases']:
            print(f"  {name}: {reason}")
        
        print(f"\n建议：")
        print(f"  1. 手动标注失败的 {len(result['failed_cases'])} 个文件")
        print(f"  2. 使用: python3 captcha_ocr_test.py label <失败的文件>")
        print(f"  3. 将标注好的文件添加到模板库以提升准确率")
    
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    exit(main())
