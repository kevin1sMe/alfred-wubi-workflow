
› 我在学习五笔输入，有这样一个网站，用于一些汉字的输入拆解，你帮我查看和分析一下它的结构：http://www.wangma.com.cn/query/wmhz1.asp。 我
  想做一个alfred 的workflow，方便我可以直接在本机操作并返回某些字是如何拆解的。比如我输入后提交有第二图，这里面的王码五笔 86/98 版的输出
  是我关注的，我应该如何实现。我注意到这个网页在查询时会要求输入验证码,可能是个图片,你需要解决这个限制


─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

• 这里把页面和请求流梳理好，并给出在 Alfred 里可复用的流程（含验证码处理思路）。

  页面结构与提交参数

  - wmhz1.asp：表单 method="post"，action="wmhz2.asp"，charset=GB2312；字段 query_hz（要查的汉字，最多4）、yanzhengma（验证码）、ok（提交
  按钮文字，可随便填）。
  - 验证码图片：<img src="/include/v.asp">，刷新按钮只是重新请求此 URL。返回的是 40x11 的 4-bit BMP（调色板颜色很少，噪声极轻），验证码长
  度 4。
  - 会话：首次 GET 会下发 ASPSESSIONID…，同一 cookie 必须贯穿“取验证码”与“提交表单”。
  - 错误提示：验证码错 -> “验证码错误。”；未填/汉字非法 -> “指定汉字错误。”。

  查询时的网络顺序

  1. GET http://www.wangma.com.cn/query/wmhz1.asp（存下 cookie）。
  2. GET http://www.wangma.com.cn/include/v.asp（同 cookie）拿到 BMP。
  3. OCR 出 4 位验证码。
  4. POST http://www.wangma.com.cn/query/wmhz2.asp，Content-Type: application/x-www-form-urlencoded，编码用 GB2312，带上 cookie（最好带
  Referer: .../wmhz1.asp）。
  5. 返回页是 HTML，使用 GB2312 解码后解析出 86/98/新世纪等编码段即可。