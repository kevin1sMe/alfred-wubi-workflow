# 双模型交叉验证自动标注方案

## 问题

- 模板匹配准确率约 70%，不是 100%
- 不想人工一个个审核所有验证码
- 需要提升准确率同时减少人工工作量

## 解决方案：双模型交叉验证

结合**模板匹配**和 **EasyOCR** 两种方法：

### 策略

#### 1. Strict（严格模式）
- ✅ 两个模型结果一致 → 自动标注
- ⚠️ 两个模型结果不一致 → 人工复核
- ⚠️ 任一模型失败 → 人工复核

**优点**：准确率最高  
**缺点**：需要人工复核的案例较多

#### 2. Balanced（平衡模式，推荐）
- ✅ 两个模型结果一致 → 自动标注
- ✅ 两个模型不一致但其中一个高置信度（>90%）→ 选择高置信度结果
- ✅ 只有一个模型成功 → 使用该结果
- ⚠️ 两个模型不一致且置信度都不高 → 人工复核

**优点**：平衡准确率和效率  
**缺点**：可能有少量误判

#### 3. Lenient（宽松模式）
- ✅ 优先使用模板匹配结果
- ✅ 模板失败时使用 EasyOCR 结果
- ⚠️ 两个都失败 → 人工复核

**优点**：人工复核最少  
**缺点**：可能准确率略低

## 使用方法

### 在 macOS 上运行（推荐）

```bash
# 1. 克隆项目
git clone git@github.com:kevin1sMe/alfred-wubi-workflow.git
cd alfred-wubi-workflow

# 2. 安装依赖
pip install requests pillow beautifulsoup4 easyocr

# 3. 从 Linux 服务器下载验证码（或直接在 macOS 上下载）
# 方式 A: 从 Linux 传输
scp -r user@linux-server:/data/chai-wubi/test_captchas ./

# 方式 B: 直接在 macOS 上下载
python3 captcha_ocr_test.py fetch --count 100 --out new_batch

# 4. 双模型交叉验证标注
python3 dual_verify.py new_batch/*.bmp --strategy balanced

# 5. 只需人工标注需要复核的案例
python3 captcha_ocr_test.py label <需要复核的文件>

# 6. 将标注好的文件添加到模板库
python3 captcha_ocr_test.py build-templates new_batch/*_*.bmp --append
```

### 试运行模式

```bash
# 先试运行看看效果
python3 dual_verify.py test_captchas/*.bmp --strategy balanced --dry-run
```

## 预期效果

假设有 100 个验证码需要标注：

| 策略 | 自动标注 | 需要人工复核 | 工作量减少 |
|------|----------|--------------|------------|
| **无辅助** | 0 | 100 | 0% |
| **Strict** | ~50-60 | ~40-50 | 50-60% |
| **Balanced** | ~70-80 | ~20-30 | 70-80% |
| **Lenient** | ~85-90 | ~10-15 | 85-90% |

## 工作流程

```bash
# 完整流程
# 1. 下载大批量验证码（在 Linux 或 macOS）
python3 captcha_ocr_test.py fetch --count 200 --out batch1

# 2. 在 macOS 上运行双模型验证（首次会下载 EasyOCR 模型）
python3 dual_verify.py batch1/*.bmp --strategy balanced

# 输出示例：
# 统计信息:
#   总计: 200
#   自动标注: 160
#   需要人工复核: 40
# 
# 人工审核工作量减少: 80%

# 3. 只需人工标注 40 个需要复核的文件（而不是 200 个）
python3 captcha_ocr_test.py label batch1/vc0001.bmp batch1/vc0005.bmp ...

# 4. 将所有标注好的文件添加到模板库
python3 captcha_ocr_test.py build-templates batch1/*_*.bmp --append

# 5. 下次准确率会更高
```

## 技术细节

### 决策逻辑（Balanced 策略）

```
如果 模板匹配 == EasyOCR:
    → 自动标注（高置信度）
    
否则如果 模板匹配置信度 > 90% 或 EasyOCR置信度 > 90%:
    → 自动标注（选择高置信度的结果）
    
否则如果 只有一个模型成功:
    → 自动标注（使用成功的结果）
    
否则:
    → 标记为需要人工复核
```

### 为什么在 macOS 上运行

1. **EasyOCR 需要较大空间**（~900MB）
2. **macOS 性能更好**（尤其是 Apple Silicon）
3. **可以使用 GPU 加速**（如果有独立显卡）
4. **不影响 Linux 服务器性能**

## 总结

使用双模型交叉验证可以：
- ✅ 将人工审核工作量减少 70-90%
- ✅ 提升整体标注准确率
- ✅ 逐步改进模板库质量
- ✅ 最终达到接近 100% 的自动化

**推荐在 macOS 上运行 `dual_verify.py`，大幅减少人工工作量！**
