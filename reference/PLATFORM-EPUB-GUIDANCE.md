# 平台侧 EPUB 规范/指南 资料清单（Apple Books 与 微信读书）

调研时间：2026-11-04。每条结论标注**来源类型**（官方 / 厂商工程博客 / 社区实测 / 未知）。

## 结论先行

| 平台 | 是否有公开的 EPUB 规范文档 | 证据强度 |
|---|---|---|
| Apple Books | **有，且非常完整**。`Apple Books Asset Guide 5.3.1`（2025-02 更新）是事实上的官方规范，逐条给了 OPF/导航/图片/字体的硬性与软性要求，并明确声明支持 EPUB 3.3 | 官方一手 |
| 微信读书 | **没有**。官方只公布过「支持哪些导入格式」和「书架书籍上限」，没有任何 EPUB 结构、CSS、目录、图片的技术规范。可采信的约束只能从厂商工程博客与社区实测里反推 | 官方零散 + 社区 |

**因此：「两个平台都有现成 guidance」这个前提不成立。** Apple 侧不需要我们重写，微信读书侧则是公开空白。

## 一、Apple Books

### 1.1 官方规范原文

- **Apple Books Asset Guide 5.3.1** — https://help.apple.com/itc/booksassetguide/en.lproj/static.html
- **Apple Books Formatting and Content Guidelines**（内容/排版层面，另一份） — https://help.apple.com/itc/applebooksstoreformatting/en.lproj/static.html
- EPUB 3 规范本体（Apple 直接引用 W3C） — https://www.w3.org/TR/epub-33/

Asset Guide 里对本项目直接生效的原话（官方）：

> Apple Books supports the EPUB 3.3 specification, and is backwards compatible with previous versions of EPUB 3.

即：Apple Books 官方支持 EPUB 3.3，并且向下兼容旧的 EPUB 3。**「用 3.3 会不会不被接受」在 Apple 这里是明确否定的。**

### 1.2 从 Asset Guide 摘出的硬性要求（逐条核对过）

| 项 | 要求 | 出处 |
|---|---|---|
| OPF `version` | 必须是 `3.0`（即使内容是 3.3） | Package Document 节 |
| OPF 必填 metadata | `dc:title` / `dc:identifier` / `dc:language` / `dcterms:modified` 四项 | The Metadata 节 |
| OPF 空白 | 元数据不得有首尾空白（5.3.1 新增） | What's New 节 |
| 导航文档 | 必须；用 `properties="nav"` 标注 | The Manifest 节 |
| toc nav | 必须存在，且只认 `epub:type="toc"` 的那个 | Table of Contents 节 |
| landmarks nav | 整个包里**只能有一个**；每个 `epub:type` 值也只能出现一次 | Landmarks 节 |
| 开卷位置 | 首个 `epub:type="ibooks:reader-start-page"`；没有则取 `bodymatter` 等 | Landmarks 节 |
| 封面图 | `properties="cover-image"`；内置封面与营销封面是两回事，营销封面要求短边 ≥1400px、RGB | Book Cover Art 节 |
| 图片写法 | 用 HTML `<img>`，**不要**用 `svg:image` 包图（旧版建议已废弃） | Interior Images 节 |
| 图片像素 | 书内单图上限 5.6 M 像素（5.2.14 从 4M 提高） | Revision History |
| alt 文本 | 不允许 `alt="none"` / `"image"` / `"page 3"` 这类；纯装饰图用 `alt=""` | Accessibility 节 |
| 字体单位 | `font-size` 用 `em`/`%`（用 `px` 会让读者无法调字号）；`line-height` 用无单位倍数 | Fonts 节 + 5.2.5 修订 |
| 脚注 | `epub:type="noteref"` + `<aside epub:type="footnote">` 可出弹窗 | Pop-up Footnotes 节 |
| 中文语言码 | 必须 `zh-Hans` / `zh-Hant`，不能只写 `zh` | 5.2.1 修订 |
| `specified-fonts` | 只在需要强制覆盖读者排版时才用 `com.apple.ibooks.display-options.xml`；固定版式才必需 | Defining Book Layout Metadata 节 |

### 1.3 对本项目成品的核对结果

- `version="3.0"` ✅ / 四项 metadata ✅ / `properties="nav"` + `properties="cover-image"` ✅
- nav 里 `toc` 与 `landmarks` 各一个 ✅
- 图片全部 `<img>`，无 `svg:image` ✅；`alt` 用图注原文或空 ✅
- `font-size` 全部 em、`line-height: 1.55` 无单位 ✅
- 书内图最大约 1.2 M 像素，低于 5.6 M ✅
- 唯一未达「建议值」的：内置封面 492×636，短边不足 1400px。这是源 PDF 里封面图的本体分辨率上限，放大无意义；营销封面另传时可换高分辨率版

## 二、微信读书

### 2.1 公开可见的一手信息

1. **支持格式与书架上限**（官方渠道转述）：txt / epub / pdf / doc / mobi / azw3 六种；书架总量上限 200 本。
   - 应用宝帮助中心（微信读书官方合作的导入入口） — https://sj.qq.com/faq/464
2. **排版引擎是自研的 HTML 树解析器**：官方工程博客称「排版引擎负责解析 EPUB 或 TXT 格式的书籍源文件」，实现基于 DTCoreText 的 HTML 树 + CSS + CoreText。
   - https://wereadteam.github.io/2016/08/23/Typesetter/
   - https://wereadteam.github.io/2020/11/11/AttributeString/

3. **最有用的一条隐性约束（厂商自曝）**：单个章节内 `<p>` 标签过多会导致 OOM 被杀。

> HTML 里 `<p>` 标签特别多，具体用户的场景里是遇到单个章节有 2w+ 的 `<p>` 标签 …… App 的内存在短时间内暴涨到 1 个 G 以上，触发系统 WatchDog 强杀。

出处在第 2 条的第二篇（2020-11-11）。这条给出了一个几乎没人写下来的量化边界：**单章不要接近 2 万个 `<p>`**。按本项目成品，最大的单文件约 500 个 `<p>`，相距两个数量级。

4. **没有任何官方 EPUB 规范**：官方帮助中心与隐私政策里只有「从本地导入书籍」这类功能描述，没有任何关于 OPF/导航/CSS/图片的技术要求。这一点是**检索后的否定结论**，不是没查到——是确实不公开。

### 2.2 社区实测（强度低，仅作参考，须自行复验）

- 单章节 1.6 MB 时，导入后出现「前 300 页正常、中间内容完全不显示」。
- 自定义字体与部分 CSS 会被剥掉或覆盖。
- 若该书在微信读书有官方正版，导入的版本可能被替换为官方版本。
- 「非会员每月 3 本导入」说法互相矛盾，存疑。

以上均无可信的官方确认，只能当经验值。

## 三、缺口分析

搜遍了 GitHub、V2EX、知乎、掘金、Stack Exchange、Apple 官方文档体系与微信读书官方站点：

- 「Apple Books 的 EPUB 要求」→ **有官方规范，质量很高**，没有重写价值。
- 「微信读书的 EPUB 要求」→ **不存在任何成体系的公开文档**，只有零散的导入教程（全是教用户点哪里，没有一条讲文件结构）。
- 「同时适配 Apple Books 与微信读书的 EPUB 制作指南」→ **完全不存在**。

## 四、本项目已实测到的、可进入未来指南的素材

这些是本次转换过程中被真实撞到的，属于「不写在任何规范里但会踩」的部分：

1. PDF 文字层的悬挂缩进（首行 x=75 / 续行 x=111）会让「按左边界分行」的段落重建全军覆没，必须用行距判定。
2. 同一行里出现一个内联加粗词，会把整段切断——段落强调级别要按字符数多数票判定，不能按「有加粗就算加粗」。
3. 项目符号可能是独立的文本对象（Courier `o`、Symbol `\uf0b7`），与正文同一行但 y 差 1–2pt；不先折叠进条目就会被排序成「…in the o sample.」。
4. 只抽栅格图会丢掉矢量绘制的图表（本书 29 页 K 线示意图全是矢量），必须按区域栅格化。
5. Nitro Pro 导出的 PDF 会把 `U+201F` 当撇号用（本书 1072 处），需要按码位修正。
6. `<p>` 数量这一条，微信读书官方博客给到了 2 万/章 的隐性上限，可以直接写进指南。

## 五、建议

**不建议现在就开新仓库做静态站。** 理由：

- Apple 侧内容全部指向官方文档，我们自己重写只会产生一个过期更快的二手副本；正确做法就是这份引用清单。
- 微信读书侧可确证的事实目前不足 10 条，撑不起一个独立站点；做成站点会让「内容少」被看见。
- 真正稀缺的是**跨平台实测报告**（带 epubcheck 结果、真机截图、失败样本），这类内容要等积累若干本书的案例才有分量。

**建议路径**：先保持这份 Markdown 随项目走；等这个项目 + 后续几本书攒出可复现的对比数据（不同切分粒度、不同目录结构在各端的表现），再决定是否独立成站。届时内容会从「10 条结论」变成「一份能被别人引用的实测矩阵」，独立仓库才有意义。

如果确实要现在就建，最小可行形态是：单页 README + `apple-books.md` / `weread.md` / `cross-platform.md` 三个文件，静态站用 MkDocs Material 或 VitePress，托管 GitHub Pages，不写构建脚本、不做版本预览。
