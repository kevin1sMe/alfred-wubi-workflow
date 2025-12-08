#!/usr/bin/env python3
import sys
from pathlib import Path
from PIL import Image

# Import existing logic
try:
    from captcha_ocr_test import CaptchaSolver, extract_label
    from auto_label import auto_label_easyocr, auto_label_tesseract
    from cnn_inference import CNNInference
except ImportError as e:
    print(f"Error: Could not import necessary modules. Make sure you are in the root directory. {e}")
    sys.exit(1)

def evaluate_round4_cumulative():
    dirs_to_check = [
        Path("captchas"), 
        Path("test_verification"), 
        Path("new_batch_60"),
        Path("batch_100_test")
    ]
    output_dir = Path("多轮测试模型对比数据")
    output_dir.mkdir(exist_ok=True)
    
    # Initialize CNN Inference (Round 4 Model)
    try:
        # Load the model trained in Round 4
        cnn_solver = CNNInference("captcha_cnn.pth")
    except Exception as e:
        print(f"Warning: CNN init failed: {e}")
        cnn_solver = None

    results = []
    
    files = []
    for d in dirs_to_check:
        if d.exists():
            files.extend(sorted(list(d.glob("*.bmp"))))
        else:
            print(f"Warning: Directory {d} not found.")

    print(f"Found {len(files)} images total.")

    correct_counts = {
        "CNN (Round 4)": 0
    }

    for p in files:
        label = extract_label(p)
        if len(label) != 4:
            print(f"Skipping {p.name}, label not found.")
            continue

        # CNN (Round 4)
        cnn_pred = ""
        if cnn_solver:
            cnn_pred, _ = cnn_solver.predict(p)

        # Check correctness
        cnn_ok = (cnn_pred == label)

        if cnn_ok: correct_counts["CNN (Round 4)"] += 1

        results.append({
            "File": p.name,
            "Dir": p.parent.name,
            "Label": label,
            "CNN": cnn_pred, "CNN_OK": "✓" if cnn_ok else "✗"
        })

    # Summary
    total = len(results)
    if total == 0:
        return

    # Markdown Report Generation
    md_lines = []
    md_lines.append("# Round 4 Cumulative Evaluation (Regression Test)")
    md_lines.append(f"\n**Dataset**: {total} images (20 + 20 + 60 + 100)")
    md_lines.append("**Model**: CNN retrained on all 200 images.")
    
    md_lines.append("\n## Summary Table")
    md_lines.append("| Model | Accuracy | Correct | Total |")
    md_lines.append("| :--- | :--- | :--- | :--- |")
    
    for model, count in correct_counts.items():
        acc = (count / total) * 100
        md_lines.append(f"| **{model}** | **{acc:.1f}%** | {count} | {total} |")

    md_lines.append("\n## Detailed Results")
    md_lines.append("| Directory | File | Label | CNN Pred | Result |")
    md_lines.append("| :--- | :--- | :--- | :--- | :--- |")
    for res in results:
        row = f"| `{res['Dir']}` | `{res['File']}` | **{res['Label']}** | {res['CNN']} | {res['CNN_OK']} |"
        md_lines.append(row)

    report_filename = "round4_cumulative_report.md"
    report_path = output_dir / report_filename
    report_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\nReport saved to {report_path.resolve()}")
    
    # Print table to console
    print("\n" + "\n".join(md_lines[6:8]))

if __name__ == "__main__":
    evaluate_round4_cumulative()
