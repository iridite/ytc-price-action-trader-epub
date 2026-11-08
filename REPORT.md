# YTC Price Action Trader → EPUB 3 转换报告

产物：`dist/YTC Price Action Trader.epub`（13.1 MB，28 个正文文档，221 条目录，405 张正文图 + 8 页图表已拆成文字与图形）

## 1. 结论

- 已交付一本可重排 EPUB，包版本 `3.0`（EPUB 3.3 规范强制 3.x 内容的 `version` 属性必须是 `"3.0"`），通过 **EPUBCheck 5.3.0：0 fatal / 0 error / 0 warning / 0 info**。
- 同时提供 EPUB 3 导航文档 `nav.xhtml` 与 EPUB 2 回退 `toc.ncx`，`mimetype` 为 ZIP 首项且 STORED 不压缩 —— 这三条同时满足微信读书与 Apple Books 最常见的兼容要求。
- **未验证**：没有在微信读书 App 与 Apple Books 里实际导入打开过。下文「已验证」项均来自工具实测，不含真机验证。Apple Books 侧的唯一真机反馈来自用户：见 §6 的表格错位问题及修法。

## 2. 源文件事实（实测）

| 项目 | 值 |
|---|---|
| 页数 | 624 |
| 页面尺寸 | 549 × 639 pt（非标准开本，单栏） |
| 文本层 | 有，可提取；正文 Times 12pt，行距 13.8pt，段距 27.6pt |
| 标题字体体系 | 36pt Cambria 卷标题页 → 26pt 章标题页 → 14pt 章内节标题 → 12.95pt Cambria 加粗蓝 小节 → 12pt Cambria 粗斜蓝 / Times 斜体 三级标题 |
| 栅格图 | 361 个唯一 xref；可见并且有效（≥100×70pt）373 处 |
| 矢量图/表 | 29 页存在成块的矢量绘图（表格、K 线示意、表单），共 31 个区域 |
| 水印 | 每页一枚 `Www.ForexWinners.net`（Calibri 蓝字 / AdobeHand 大字）+ 页外 52×39 图标，全部剔除 |

## 3. 处理流程

`build/extract.py` → `build/flow.py`（PDF → 阅读顺序 JSON + 图片）→ `build/mkepub.py`（JSON → EPUB）。

1. **阅读顺序重建**：按 y 再按 x 排序文本行、栅格图、矢量块，三类元素统一排队，避免图形与文字错位。
2. **段落还原**：以行距为判据（13.8pt = 同段，27.6pt = 新段），而非左边界。这条是必需的：本书有大量悬挂缩进的编号项（首行 x=75，续行 x=111），只靠 x 对齐会把每个列表项切成多段。
3. **样式归一**：`TimesNewRoman` 与 `Times-Roman` 视为同一字体；带内联粗体的行按「字符数多数票」判定段落强调级别，否则一行里出现一个加粗词就会把整段切断。
4. **矢量图形栅格化**：31 个矢量区域按 3× 渲染成 PNG 并剔除被覆盖的文字块——只抽栅格图会丢掉 29 页的 K 线示意图和表格。
5. **双栏图表的行级重建**（`build/tables.py`）：287–290、616–619 这 8 页是「图压文字」的双栏表。按行分隔线的固定宽度（345.6pt）识别行边界，把右侧文字抽成段落，图形区域先用 redaction 抹掉本页文字再 4× 渲染，最后抹掉落在裁剪框内的栏分隔线。识别条件全部来自几何量，没有写死页码。
5. **标题合并**：跨行的章标题（如 `Chapter Four –` + `Strategy – YTC Price Action Trader`）与节标题按「同页 + 同字号 + 行距 < 1.6 倍字号」合并成一条。
6. **字符修复**：`U+201F → ’`、`U+201E → ‘`（Nitro 导出的引号错位，1072 处）、Symbol/Wingdings/Courier 项目符号 → `•`。Courier 的 `o` 是独立的圆形项目符号文本对象，与条目文字同一行但 y 差 1.5pt，必须先折叠进条目首行再排序，否则会出现「…in the o sample.」这类断句。
7. **切分**：按 卷 → 章 → 节 分层，单 XHTML 目标 ≤110 KB，在节/小节边界处切；最大 112 KB。

## 4. 兼容性取舍（证据来源）

| 决策 | 依据 |
|---|---|
| `version="3.0"` | EPUB 3.3 规范要求所有 3.x 出版物的 `version` 属性恒为 `"3.0"`，阅读器无从依据版本号判断「不支持 3.3」 |
| nav + NCX 双目录 | NCX 在 EPUB 3 中已非必需，但 EPUB 2 阅读链路仍读它；你上一本《主权个人》EPUB 也是双目录且可正常导入 |
| 不内嵌字体 | 微信读书会剥掉/覆盖自定义字体；内嵌只会增大体积。采用 `-webkit-hyphens: auto` 交给阅读器排版 |
| 每节一个 XHTML（≤112 KB） | 社区实测单文档 1.6 MB 时微信读书出现「前 300 页正常、中间不显示」；你的《主权个人》最大单文件 182 KB 也可用，但本书按 110 KB 切更稳 |
| 图片 JPEG 为主、矢量图 PNG | 栅格原图本身是 JPEG（不二次转码，只做 >1500px 的等比缩小）；矢量线稿用 PNG 避免 JPEG 振铃 |
| 图片全部重命名为 `imgNNNN.jpg` / `vecNNNN.png` | 规避原 PDF 的资源名与阅读器兼容问题 |
| 无 `com.apple.ibooks.display-options.xml` | 该文件只在需要强制指定字体/固定版式时有意义；本书不内嵌字体，加了反而可能锁死 Apple Books 的字体切换 |

## 5. 已验证 / 未验证

已验证（工具实测）：
- EPUBCheck 5.3.0 全零。
- 441 个 ZIP 条目，内部链接 0 处失效（逐条 `href`/`src` 解析比对）。
- `content.opf` / `nav.xhtml` / `toc.ncx` / `container.xml` 均 XML 良构。
- `mimetype` 是第 0 项且 `compress_type=0`。
- Chromium 渲染（含强制 body=360px 的窄屏复现）：封面按比例缩放不裁切、正文左右留白正常、图注斜体居中、项目符号列表正常、四级目录层级正确、`document.scrollWidth` 与视口一致（无横向溢出）。
- 段落接缝全文扫描（4,265 个相邻 `p`）：以「前段不以终止标点结尾 + 后段小写开头」判据检出 0 处残余断裂。
- 图注结构：404 个 `figure` 中 343 个带图注，图注一律是块级 `<p class="figcap">` 而非 `figcaption`，不依赖阅读器对 `<figure>` 的块级语义。
- 目录与正文坐标：与 v1.0.2 相比，三个含笔记的正文文件（ch-01/02/03）纯文本长度逐字节相同，42 条可定位划线在新旧包中的文本偏移差全部为 0。
- 正文文本量：EPUB 55.8 万非空白字符 / PDF 56.7 万 = **98.4%**。差额是被剔除的水印和少数仍以整页图形保留的表单页标签（如 544 页）。

未验证：
- 微信读书导入后的实际排版、目录识别、图片加载。
- Apple Books 导入与书库展示（用户已在 Apple Books 打开验证过表格问题，其余未验）。
- 这两个平台对 221 条四级目录的折叠表现；微信读书侧已确认能显示 `x.y.z` 子条目。
- 微信读书对 `<figure>` 内块级字符的排版细节：本轮把图注改成 `<p class="figcap">` 是为了绕开它对 `figcaption` 的 inline 处理，真机效果待复验。

## 6. 已知取舍

- 287–290、616–619 这 8 页的「形态参考表」原本是「矢量 K 线图 + 右侧说明文字」的双栏表格，且**源 PDF 里图就已经压到文字上**（用 poppler 独立渲染复现，确认不是截取问题）。已改为逐行重建：文字抽成真正的段落（可检索、可换行），图形部分先把该页文字做 redaction 抹掉再按行裁剪渲染，最后按「图 → 形态名 → 说明」竖排。代价是失去表格的左右栏版式，换来手机窄屏可读。
- 544 等表单页仍整块保留为图片：那是空白待填模板，竖排重排没有意义。
- 原书 PDF 目录页（第 3–8 页）的页码本身是错的（每卷重新计数），已整段丢弃，改用重建目录。
- 章内 439 条无编号的斜体小标题不做目录项（否则目录会变成 600+ 条），但 72 条带 `x.y.z` 编号的小节全部作为第 4 层收入；两者在正文里都保留为 `h3`，视觉上不做区分。
- 封面用 PDF 内嵌的 492×636 原生图（页面上那张是全页裁切版，右下被页边切掉，不能用）。

## 7. 复现

```bash
cd ~/Documents/ytc-epub
.venv/bin/python build/flow.py      # PDF → build/flow.json + build/media（约 80s）
.venv/bin/python build/mkepub.py    # → dist/YTC Price Action Trader.epub
/opt/homebrew/opt/openjdk/bin/java -jar tools/epubcheck-5.3.0/epubcheck.jar "dist/YTC Price Action Trader.epub"
```

`build/flow.py` 会把逐页解析结果缓存到 `build/raw_pages.json`，调排版规则时不必重跑 PDF 解析（`--force` 强制重算）。

## 8. 笔记迁移记录（2026-11-08）

这本书换过三个 `bookId`，笔记逐次迁移，每次都做全量核对：

| 代 | bookId | 状态 |
|---|---|---|
| A | `CB_3e60aA0Y71zX77T75D75DGkW` | 已清空（45 划线 + 30 想法全删） |
| B | `CB_4VbGQhGQn27l77R75DDqHBWv` | 已清空（4 划线 + 2 想法全删） |
| C | `CB_GWC0bM0cE0Se77Y75D75DArw78J` | 当前在架，45 划线 + 30 想法 |

- 重新导入不复用 `bookId`；`chapterUid` 由包内文件与切分边界决定，实测 A→C 的 31 章 1:1 映射成功。
- `range` 原样复用即可，前提是新包正文文字未变：本次除新增 72 个锚点 `id` 外正文逐字节相同，42 条可定位划线的文本偏移差全为 0。
- 核对判据：按 `(chapterUid, range)` 比对 `markText` 与想法的 `content`，45/45 与 30/30 全一致。
- 工具：`~/Documents/weread-ytc-notes/migrate.py`（同一份也收在 foundry 的 `Skills/weread-note-migration/`）；原始响应与导出落在同目录。
