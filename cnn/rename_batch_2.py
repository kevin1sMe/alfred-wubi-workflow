#!/usr/bin/env python3
import re
from pathlib import Path

def rename_files():
    report_path = Path("batch_100_test_2_report_v3.md")
    target_dir = Path("batch_100_test_2")
    
    if not report_path.exists() or not target_dir.exists():
        print("Error: Report or Directory not found.")
        return

    content = report_path.read_text(encoding="utf-8")
    
    # Regex to parses lines like: | vc0000.bmp | 0000 | 8681 | 8681 | 8684 | 8681 | ✅ Trusted |
    # We want group 1 (filename) and group 6 (Custom CNN prediction)
    # The table columns seem to be: | File | Original | Template | EasyOCR | Tesseract | Custom CNN | Status |
    # Let's count pipes.
    # | (empty) | File (1) | Original (2) | Template (3) | EasyOCR (4) | Tesseract (5) | Custom CNN (6) | Status (7) |
    
    lines = content.splitlines()
    renamed_count = 0
    
    print("Starting renaming process...")
    
    for line in lines:
        if not line.strip().startswith("|") or "File" in line or "---" in line:
            continue
            
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 8:
            continue
            
        filename = parts[1]
        cnn_pred = parts[6]
        
        # Validate filename and prediction
        if not filename.endswith(".bmp") or not cnn_pred.isdigit():
            print(f"Skipping invalid line: {filename} -> {cnn_pred}")
            continue
            
        # Construct new filename: vcXXXX_LABEL.bmp
        # But wait, current filename is vcXXXX.bmp. 
        # We want to preserve the serial number.
        stem = filename.replace(".bmp", "")
        new_filename = f"{stem}_{cnn_pred}.bmp"
        
        old_path = target_dir / filename
        new_path = target_dir / new_filename
        
        if old_path.exists():
            old_path.rename(new_path)
            renamed_count += 1
            # print(f"Renamed: {filename} -> {new_filename}")
        else:
            # Check if already renamed
            if new_path.exists():
                print(f"Already renamed: {new_filename}")
            else:
                print(f"File not found: {filename}")

    print(f"Renaming complete. Renamed {renamed_count} files.")

if __name__ == "__main__":
    rename_files()
