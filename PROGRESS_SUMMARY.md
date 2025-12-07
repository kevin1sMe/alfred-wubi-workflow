# 项目进度总结 - 王码五笔查询工具集

**最后更新时间**: 2025-12-07 13:44  
**当前状态**: Linux 开发完成，准备迁移到 macOS 继续

---

## 📋 项目概述

这是一个王码五笔查询工具集，主要功能：
1. 自动识别 wangma.com.cn 网站的验证码
2. 查询汉字的五笔 86/98/新世纪编码
3. 下载汉字拆解图片
4. 提供 Alfred Workflow 集成

**Git 仓库**: `git@github.com:kevin1sMe/alfred-wubi-workflow.git`

---

## 🎯 核心发现

### 验证码识别准确率对比

| 方法 | 准确率 | 说明 |
|------|--------|------|
| **模板匹配** | ~70% | 当前方法，需要改进 |
| **Tesseract OCR** | ~25% | 效果差，不推荐 |
| **EasyOCR** | 待测试 | 需要在 macOS 上测试 |
| **双模型验证** | 预计 90%+ | 推荐方案 |

### 关键问题

1. ❌ 模板匹配准确率只有 70%，不是之前测试的 100%
2. ❌ Linux 服务器磁盘空间不足，无法安装 EasyOCR（需要 900MB）
3. ✅ 创建了双模型交叉验证方案，可以减少 70-90% 的人工审核工作量

---

## 📁 项目文件结构

```
/data/chai-wubi/
├── captcha_ocr_test.py      # 验证码识别、标注、评估工具
├── wubi_query.py             # 五笔编码查询脚本
├── alfred_wubi.py            # Alfred Workflow 集成
├── batch_label.py            # 使用模板匹配批量标注（简单）
├── auto_label.py             # Tesseract/EasyOCR 自动标注
├── dual_verify.py            # 双模型交叉验证（推荐）⭐
├── captcha_templates/        # 80 个验证码模板（0-9 每个数字多个样本）
├── README.md                 # 项目说明
├── TECH.md                   # 技术文档
├── AUTO_LABEL_GUIDE.md       # 自动标注方案对比
├── DUAL_VERIFY_GUIDE.md      # 双模型验证使用指南⭐
└── .gitignore                # Git 忽略配置
```

---

## 🚀 下一步行动（在 macOS 上）

### 1. 克隆项目到 macOS

```bash
# 在 macOS 终端
git clone git@github.com:kevin1sMe/alfred-wubi-workflow.git
cd alfred-wubi-workflow
```

### 2. 安装依赖

```bash
# 基础依赖（必需）
pip3 install requests pillow beautifulsoup4

# EasyOCR（用于双模型验证，首次运行会下载模型 ~100MB）
pip3 install easyocr
```

### 3. 测试双模型交叉验证

```bash
# 方式 A: 从 Linux 服务器传输已有验证码
scp -r user@linux-server:/data/chai-wubi/test_captchas ./

# 方式 B: 直接在 macOS 上下载新验证码
python3 captcha_ocr_test.py fetch --count 50 --out test_batch

# 运行双模型交叉验证（推荐 balanced 策略）
python3 dual_verify.py test_batch/*.bmp --strategy balanced

# 先试运行看看效果
python3 dual_verify.py test_batch/*.bmp --strategy balanced --dry-run
```

### 4. 人工标注需要复核的案例

```bash
# dual_verify.py 会输出需要人工复核的文件列表
# 只需标注这些文件（通常只有 20-30%）
python3 captcha_ocr_test.py label <需要复核的文件>
```

### 5. 将标注好的文件添加到模板库

```bash
# 将新标注的验证码添加到模板库，提升准确率
python3 captcha_ocr_test.py build-templates test_batch/*_*.bmp --append

# 提交到 Git
git add captcha_templates/
git commit -m "Add new captcha templates"
git push
```

---

## 🔧 双模型交叉验证策略

### Balanced 策略（推荐）

**决策逻辑**:
1. ✅ 模板匹配 == EasyOCR → 自动标注（高置信度）
2. ✅ 两者不一致但其中一个置信度 > 90% → 选择高置信度结果
3. ✅ 只有一个模型成功 → 使用该结果
4. ⚠️ 两者不一致且置信度都不高 → 人工复核

**预期效果**:
- 自动标注: 70-80%
- 需要人工复核: 20-30%
- **人工工作量减少 70-80%**

### 其他策略

- **Strict**: 只有两个模型完全一致才自动标注（准确率最高，但需要复核的多）
- **Lenient**: 优先使用模板匹配结果（自动标注最多，但可能有误判）

---

## 📊 工作流程示例

```bash
# 完整的批量标注流程

# 1. 下载 200 个验证码
python3 captcha_ocr_test.py fetch --count 200 --out batch1

# 2. 双模型交叉验证（在 macOS 上）
python3 dual_verify.py batch1/*.bmp --strategy balanced

# 输出示例：
# 统计信息:
#   总计: 200
#   自动标注: 160 (80%)
#   需要人工复核: 40 (20%)
# 
# 人工审核工作量减少: 80%

# 3. 只需人工标注 40 个需要复核的文件
python3 captcha_ocr_test.py label batch1/vc0001.bmp batch1/vc0005.bmp ...

# 4. 将所有标注好的文件添加到模板库
python3 captcha_ocr_test.py build-templates batch1/*_*.bmp --append

# 5. 评估新模板库的准确率
python3 captcha_ocr_test.py fetch --count 50 --out test_new
python3 batch_label.py test_new/*.bmp
python3 captcha_ocr_test.py eval test_new/*.bmp

# 6. 提交改进
git add captcha_templates/
git commit -m "Improve template library, add X new samples"
git push
```

---

## 🎓 技术要点

### 为什么在 macOS 上运行

1. **磁盘空间**: EasyOCR 需要 ~900MB，Linux 服务器空间不足
2. **性能**: macOS 性能更好（尤其是 Apple Silicon 可以用 Metal 加速）
3. **开发体验**: macOS 上安装依赖更方便
4. **不影响服务器**: Linux 服务器只用来运行查询服务

### 模板匹配为什么只有 70% 准确率

可能的原因：
1. 验证码样式有变化
2. 模板库覆盖不全
3. 某些数字的变体没有收录

**解决方案**: 通过双模型验证 + 人工复核 + 持续补充模板库，逐步提升到 90%+

### 双模型验证的优势

1. **减少人工工作量**: 70-90%
2. **提升准确率**: 通过交叉验证发现不确定的案例
3. **持续改进**: 每次标注都补充模板库
4. **最终目标**: 达到接近 100% 的自动化

---

## 📝 重要提醒

### 首次在 macOS 上运行

1. **EasyOCR 首次运行会下载模型** (~100MB)，需要等待几分钟
2. **确保网络畅通**，模型下载可能需要时间
3. **如果下载失败**，可以设置代理或使用国内镜像

### 文件同步

- **Linux → macOS**: 使用 `scp` 或 `git pull`
- **macOS → Linux**: 使用 `git push` 同步模板库更新
- **建议**: 模板库改进后及时提交到 Git

### 性能优化

- **Apple Silicon (M1/M2/M3)**: EasyOCR 会自动使用 Metal 加速
- **Intel Mac**: 可能较慢，建议使用 balanced 策略
- **如果太慢**: 可以先用 batch_label.py 快速标注，然后只对失败案例使用双模型验证

---

## 🔗 相关文档

- `DUAL_VERIFY_GUIDE.md` - 双模型验证详细指南
- `AUTO_LABEL_GUIDE.md` - 所有自动标注方案对比
- `README.md` - 项目基本使用说明
- `TECH.md` - 技术实现细节

---

## ✅ 已完成的工作

1. ✅ 创建了基于模板匹配的验证码识别系统
2. ✅ 实现了失败案例保存功能 (`--save-failed`)
3. ✅ 测试了 Tesseract OCR（效果差，25% 准确率）
4. ✅ 创建了批量标注工具 (`batch_label.py`)
5. ✅ 创建了双模型交叉验证工具 (`dual_verify.py`)
6. ✅ 初始化 Git 仓库并推送到 GitHub
7. ✅ 包含 80 个验证码模板样本

---

## 🎯 下一步目标

1. 在 macOS 上测试 `dual_verify.py`
2. 验证双模型交叉验证的实际效果
3. 批量标注 200-500 个验证码
4. 将新样本添加到模板库
5. 评估改进后的准确率（目标 90%+）
6. 最终集成到 Alfred Workflow

---

## 💡 快速参考

```bash
# 在 macOS 上的快速开始命令
git clone git@github.com:kevin1sMe/alfred-wubi-workflow.git
cd alfred-wubi-workflow
pip3 install requests pillow beautifulsoup4 easyocr
python3 captcha_ocr_test.py fetch --count 50 --out test
python3 dual_verify.py test/*.bmp --strategy balanced --dry-run
```

---

**祝在 macOS 上工作顺利！如有问题，参考 `DUAL_VERIFY_GUIDE.md` 文档。**
