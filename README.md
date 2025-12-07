# 王码五笔查询工具集

本仓库封装了对 wangma.com.cn 查询接口的脚本，自动解决验证码，输出五笔/数字王码编码，并支持下载拆解图片供 Alfred Workflow 展示。

## 主要脚本

- `captcha_ocr_test.py`：下载、标注、构建验证码模板，内置 OCR 解码器。
- `wubi_query.py`：命令行查询单字，输出五笔 86/98/新世纪、数字王码 5/6/9 键、笔画序列，可下载拆解 BMP。
- `alfred_wubi.py`：Alfred Script Filter 输出 JSON，附带拆解图片（icon/quicklook）。

## 依赖

- Python 3
- `requests`、`Pillow`、`beautifulsoup4`

建议在 Workflow 目录内创建虚拟环境：
```
python3 -m venv .venv
.venv/bin/pip install requests pillow beautifulsoup4
```

## 使用示例

### 命令行查询
```
python3 wubi_query.py 码 --max-retry 8 --download-imgs components_码
```
输出编码并将拆解图片保存到 `components_码/`。

### Alfred Script Filter（示例调用）
```
/.venv/bin/python3 alfred_wubi.py 码 --cache-dir alfred_cache
```
将在 JSON 中包含编码行和每个部件的图片路径（绝对路径，方便 icon/quicklook）。

## 过滤展示（--only 参数）

`alfred_wubi.py` 支持通过 `--only` 选择要展示的字段，逗号分隔（不区分大小写）：
- `summary`：总体汇总行
- 编码：`num5`, `num6`, `num9`, `wb86`, `wb98`, `wbx`(新世纪), `strokes`
- 拆解图片：`num6_parts`, `num9_parts`, `wb86_parts`, `wb98_parts`, `wbx_parts`

示例：仅展示五笔 86 编码及其拆解
```
python3 alfred_wubi.py 你 --only wb86,wb86_parts
```

## 注意事项

- 验证码依赖 `captcha_templates/`，若识别不稳，可追加模板或提高 `--max-retry`。
- 提交表单使用 GB2312 编码，保持代码页设置即可。
- 下载的拆解 BMP 使用绝对路径，方便在 Alfred 中直接作为 icon/quicklook。 
