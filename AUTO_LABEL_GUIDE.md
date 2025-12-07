# 验证码自动标注方案对比

## 可用方案

### 方案 1: batch_label.py（最推荐 ⭐⭐⭐⭐⭐）

**使用现有的模板匹配方法批量标注**

**优点：**
- ✅ 准确率最高（95-100%）
- ✅ 速度最快
- ✅ 无需额外依赖
- ✅ 已经过充分测试

**使用方法：**
```bash
# 批量自动标注
python3 batch_label.py test_captchas/*.bmp

# 试运行（预览结果）
python3 batch_label.py test_captchas/*.bmp --dry-run
```

**工作流程：**
```bash
# 1. 下载验证码
python3 captcha_ocr_test.py fetch --count 50 --out new_captchas

# 2. 批量自动标注（使用模板匹配）
python3 batch_label.py new_captchas/*.bmp

# 3. 只需人工标注失败的案例（通常很少）
python3 captcha_ocr_test.py label new_captchas/vc*.bmp  # 未标注的文件

# 4. 将失败案例添加到模板库
python3 captcha_ocr_test.py build-templates new_captchas/*_*.bmp --append
```

---

### 方案 2: auto_label.py --method tesseract（不推荐）

**使用 Tesseract OCR**

**缺点：**
- ❌ 准确率低（25%）
- ❌ 对小图片效果差

**仅用于验证：**
```bash
# 验证模式：对比 OCR 和模板识别结果
python3 auto_label.py captchas/*.bmp --verify
```

---

### 方案 3: auto_label.py --method easyocr（可尝试）

**使用 EasyOCR（深度学习）**

**安装：**
```bash
pip install easyocr
```

**优点：**
- ✅ 基于深度学习，可能比 Tesseract 准确
- ✅ 支持多种语言

**缺点：**
- ⚠️ 首次运行需下载模型（~100MB）
- ⚠️ 速度较慢
- ⚠️ 需要测试效果

**使用方法：**
```bash
# 使用 EasyOCR 自动标注
python3 auto_label.py test_captchas/*.bmp --method easyocr

# 验证模式
python3 auto_label.py captchas/*.bmp --method easyocr --verify
```

---

### 方案 4: PaddleOCR（国产，可选）

**百度开源的 OCR 引擎**

**安装：**
```bash
pip install paddlepaddle paddleocr
```

**优点：**
- ✅ 对数字识别效果好
- ✅ 有轻量级模型

**缺点：**
- ⚠️ 需要额外安装
- ⚠️ 需要测试效果

---

### 方案 5: OpenAI Vision API（最准确但有成本）

**使用 GPT-4 Vision**

**优点：**
- ✅ 准确率极高（接近100%）
- ✅ 无需训练

**缺点：**
- ❌ 需要 API key
- ❌ 需要网络连接
- ❌ 有费用（约 $0.01/张）

**实现示例：**
```python
import base64
import openai

def label_with_gpt4_vision(image_path):
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode()
    
    response = openai.ChatCompletion.create(
        model="gpt-4-vision-preview",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "这是一个4位数字验证码，请只输出这4个数字，不要有任何其他内容。"},
                {"type": "image_url", "image_url": {"url": f"data:image/bmp;base64,{image_data}"}}
            ]
        }]
    )
    return response.choices[0].message.content.strip()
```

---

## 推荐方案

### 🥇 首选：batch_label.py（模板匹配）

**理由：**
1. 准确率最高（95-100%）
2. 速度最快
3. 已经过验证
4. 无需额外依赖

**适用场景：**
- 日常使用
- 批量处理
- 追求准确率

### 🥈 备选：EasyOCR（如果想尝试）

**理由：**
1. 可能比 Tesseract 准确
2. 基于深度学习

**适用场景：**
- 想尝试其他方案
- 对比测试

### 🥉 可选：OpenAI Vision（如果不在意成本）

**理由：**
1. 准确率最高
2. 无需训练

**适用场景：**
- 一次性大批量标注
- 追求极致准确率
- 不在意成本

---

## 测试对比

| 方案 | 准确率 | 速度 | 成本 | 推荐度 |
|------|--------|------|------|--------|
| batch_label.py | 95-100% | 极快 | 免费 | ⭐⭐⭐⭐⭐ |
| Tesseract | 25% | 快 | 免费 | ⭐ |
| EasyOCR | 待测试 | 慢 | 免费 | ⭐⭐⭐ |
| PaddleOCR | 待测试 | 中等 | 免费 | ⭐⭐⭐ |
| GPT-4 Vision | ~100% | 中等 | $0.01/张 | ⭐⭐⭐⭐ |

---

## 快速开始

**推荐使用 batch_label.py：**

```bash
# 1. 批量标注
python3 batch_label.py test_captchas/*.bmp

# 2. 查看结果
ls test_captchas/*_*.bmp

# 3. 人工标注失败的案例（如果有）
python3 captcha_ocr_test.py label test_captchas/vc*.bmp
```

完成！
