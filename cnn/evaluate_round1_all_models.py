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

def evaluate_round1_all():
    captchas_dir = Path("captchas")
    if not captchas_dir.exists():
        print(f"Error: Directory {captchas_dir} does not exist.")
        sys.exit(1)

    # Initialize Template Matching Solver
    try:
        template_solver = CaptchaSolver.from_dir()
    except Exception as e:
        print(f"Warning: Template Matching init failed: {e}")
        template_solver = None

    # Initialize CNN Inference (Self-Consistency)
    try:
        cnn_solver = CNNInference("captcha_cnn.pth")
    except Exception as e:
        print(f"Warning: CNN init failed: {e}")
        cnn_solver = None

    results = []
    files = sorted(list(captchas_dir.glob("*.bmp")))
    print(f"Found {len(files)} images in {captchas_dir}")

    correct_counts = {
        "Template Matching": 0,
        "EasyOCR": 0,
        "Tesseract": 0,
        "CNN (Round 1)": 0
    }

    for p in files:
        label = extract_label(p)
        if len(label) != 4:
            continue

        # 1. Template Matching
        tm_pred = ""
        if template_solver:
            try:
                tm_pred = template_solver.solve(Image.open(p))
            except:
                tm_pred = ""
        
        # 2. EasyOCR
        try:
            eo_pred, _ = auto_label_easyocr(p)
        except:
            eo_pred = ""

        # 3. Tesseract
        try:
            te_pred, _ = auto_label_tesseract(p)
        except:
            te_pred = ""

        # 4. CNN
        cnn_pred = ""
        if cnn_solver:
            cnn_pred, _ = cnn_solver.predict(p)

        # Check correctness
        tm_ok = (tm_pred == label)
        eo_ok = (eo_pred == label)
        te_ok = (te_pred == label)
        cnn_ok = (cnn_pred == label)

        if tm_ok: correct_counts["Template Matching"] += 1
        if eo_ok: correct_counts["EasyOCR"] += 1
        if te_ok: correct_counts["Tesseract"] += 1
        if cnn_ok: correct_counts["CNN (Round 1)"] += 1

        results.append({
            "File": p.name,
            "Label": label,
            "TM": tm_pred, "TM_OK": "✓" if tm_ok else "✗",
            "EO": eo_pred, "EO_OK": "✓" if eo_ok else "✗",
            "TE": te_pred, "TE_OK": "✓" if te_ok else "✗",
            "CNN": cnn_pred, "CNN_OK": "✓" if cnn_ok else "✗"
        })

    # Summary
    total = len(results)
    if total == 0:
        return

    # Markdown Report Generation
    md_lines = []
    md_lines.append("# Round 1 All Models Evaluation")
    md_lines.append(f"\n**Dataset**: {total} images from `{captchas_dir}`")
    
    md_lines.append("\n## Summary Table")
    md_lines.append("| Model | Accuracy | Correct | Total |")
    md_lines.append("| :--- | :--- | :--- | :--- |")
    
    # Sort models by accuracy desc
    sorted_models = sorted(correct_counts.items(), key=lambda x: x[1], reverse=True)
    
    for model, count in sorted_models:
        acc = (count / total) * 100
        md_lines.append(f"| **{model}** | **{acc:.1f}%** | {count} | {total} |")

    md_lines.append("\n## Detailed Comparison")
    md_lines.append("| File | Label | Template Match | EasyOCR | Tesseract | CNN (R1) |")
    md_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for res in results:
        row = f"| `{res['File']}` | **{res['Label']}** | "
        row += f"{res['TM']} {res['TM_OK']} | "
        row += f"{res['EO']} {res['EO_OK']} | "
        row += f"{res['TE']} {res['TE_OK']} | "
        row += f"{res['CNN']} {res['CNN_OK']} |"
        md_lines.append(row)

    report_path = Path("round1_all_models_report.md")
    report_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\nReport saved to {report_path.resolve()}")
    
    # Print table to console
    print("\n" + "\n".join(md_lines[4:10]))

if __name__ == "__main__":
    evaluate_round1_all()
