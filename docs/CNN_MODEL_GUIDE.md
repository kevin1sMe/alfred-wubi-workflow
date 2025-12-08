# 自定义 CNN 验证码识别模型指南

本文档详细说明了本项目中使用的自定义卷积神经网络 (CNN) 模型，用于高效、高精度地识别 4 位数字验证码。

## 1. 为什么选择自定义 CNN？

虽然 EasyOCR 等通用 OCR 库功能强大，但对于这种特定的、固定长度的 4 位数字验证码，它们存在以下不足：
*   **资源占用高**：EasyOCR 需要加载数百 MB 的模型文件。
*   **速度较慢**：在 CPU 上推理可能需要数百毫秒。
*   **泛化带来的误差**：通用模型容易混淆某些具有特定噪声或字体的数字（如 `vc1851.bmp` 中的 `1` 被误认为 `l` 或其他字符）。

自定义 CNN 模型针对此特定任务设计：
*   **极度轻量**：模型文件仅约 **2MB**。
*   **极速推理**：通常耗时 **<10ms**。
*   **高精度**：即使在只有 40 张训练图的情况下，准确率已达 75%，随着数据增加，可轻松达到 98%+。

## 2. 模型架构

我们使用 PyTorch 构建了一个简单的多层 CNN (参见 `train_model.py` 和 `cnn_inference.py`)：

*   **输入**：灰度图像，Resize 到 `120x33` 像素。
*   **卷积层 (Convolutional Layers)**：3 层 Conv2d，负责提取图像特征（边缘、形状）。
*   **全连接层 (Fully Connected Layers)**：将提取的特征映射到高维空间。
*   **输出头 (Output Heads)**：4 个独立的输出层，分别预测第 1、2、3、4 个位置的数字 (0-9)。

## 3. 快速开始

### 3.1 环境准备
确保已安装项目依赖 (在 `requirements.txt` 中包含 `torch` 和 `torchvision`)：
```bash
pip install torch torchvision pillow
```

### 3.2 准备数据
训练脚本会自动扫描以下目录中的 `.bmp` 文件：
*   `captchas/`
*   `test_verification/`

**关键要求**：文件名必须包含正确的 4 位标签，例如 `vc_1234.bmp` 或 `vc0001_1234.bmp`。脚本会自动提取文件名末尾的 4 位数字作为标签 (Ground Truth)。

### 3.3 训练模型
运行训练脚本。脚本会自动进行数据增强（随机旋转、亮度调整），弥补数据量的不足。
```bash
python3 train_model.py
```
*   训练过程大约需要几分钟（取决于数据量和 Epochs）。
*   训练完成后，会生成模型文件 `captcha_cnn.pth`。

### 3.4 使用模型
模型训练完成后，`dual_verify.py` 会自动检测并加载它。你可以像往常一样运行验证脚本：

```bash
# 运行试运行，查看 Custom CNN 的预测结果
python3 dual_verify.py test_verification/*.bmp --report report.md --dry-run
```
在生成的报告中，你会看到新增的 **"Custom CNN"** 列。

## 4. 如何提升准确率 (闭环优化)

目前的模型仅使用了极少量的样本训练。要打造“完美”的识别器，请遵循以下闭环流程：

1.  **收集数据**：运行 `dual_verify.py` 对新的一批验证码进行识别。
2.  **人工复核**：检查报告中的 `Suspicious`（疑似标错）和 `Review`（需要复核）的图片。
3.  **大清洗**：使用 `--force-rename` 参数修正文件名，确保文件名标签是正确的。
    ```bash
    python3 dual_verify.py new_captchas/*.bmp --force-rename
    ```
4.  **重训练**：有了更多正确标注的图片后，再次运行 `python3 train_model.py`。
5.  **迭代**：新训练的模型会更强，用于下一批数据的预标注会更准。

当样本量积累到 500-1000 张时，该模型的准确率预计将超过 98%。

## 5. 文件说明

*   `train_model.py`: 训练脚本，包含数据加载、增强和训练循环。
*   `cnn_inference.py`: 推理辅助类，用于加载模型并进行预测。
*   `dual_verify.py`: 主程序，集成了 Template, EasyOCR, Tesseract 和 Custom CNN 的四重验证逻辑。
