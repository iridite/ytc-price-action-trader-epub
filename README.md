# ytc-price-action-trader-epub

把 Lance Beggs 的《YTC Price Action Trader》PDF 转制成可重排 EPUB 3 的**可复现构建管线**，目标是同时适配 Apple Books 与微信读书。

## 下载

- 最新版 EPUB：[YTC-Price-Action-Trader.epub](https://github.com/iridite/ytc-price-action-trader-epub/releases/latest/download/ytc-price-action-trader.epub)

## 来源与说明

- 源文件是一本在售的英文交易类电子书（Nitro Pro 7 于 2021 年导出的 624 页 PDF）。**仓库里不放 PDF 正文，也不以任何形式重新分发原始 PDF**。
- 版权归作者 Lance Beggs / YourTradingCoach.com 所有。

## 仓库结构

```
scripts/
  flow.py        PDF → 阅读顺序 JSON + 图片（~75s，结果缓存到 build/）
  tables.py      8 页「图压文字」双栏表的行级重建
  mkepub.py      JSON → dist/*.epub（OPF / nav / NCX / CSS / 封面）
reference/
  PLATFORM-EPUB-GUIDANCE.md   Apple Books 与微信读书的平台侧规范资料清单
REPORT.md        转换报告：源文件实测数据、决策依据、已验证/未验证
build/           中间产物（忽略）
dist/            成品（忽略，走 releases）
```

## 构建

需要本机已有源 PDF（默认读仓库根目录的 `source.pdf`）。

```bash
uv venv --python 3.12
uv pip install -e .          # 或 uv sync
.venv/bin/python scripts/flow.py     # → build/flow.json + build/media
.venv/bin/python scripts/mkepub.py   # → dist/YTC Price Action Trader.epub
```

`flow.py` 会把逐页解析结果缓存成 `build/raw_pages.json`，之后调排版规则不必重跑 PDF 解析；需要强制重算时删掉该缓存即可。

## 校验

```bash
# epubcheck 5.3.0（tools/ 目录自行下载，不入库）
curl -L -o /tmp/ec.zip https://github.com/w3c/epubcheck/releases/download/v5.3.0/epubcheck-5.3.0.zip
unzip -q /tmp/ec.zip -d tools/
/opt/homebrew/opt/openjdk/bin/java -jar tools/epubcheck-5.3.0/epubcheck.jar "dist/YTC Price Action Trader.epub"
```

当前结果：`0 fatals / 0 errors / 0 warnings / 0 infos`。

## 成品规格

| 项目 | 值 |
|---|---|
| 包版本 | EPUB 3.0（EPUB 3.3 规范要求 3.x 内容的 `version` 恒为 `"3.0"`） |
| 目录 | `nav.xhtml` + `toc.ncx` 双目录，185 条四级（卷 → 章 → 编号节 → 带 `x.y.z` 编号的小节） |
| 文档数 | 32 个 XHTML（30 个正文 + 目录 + 封面），单文件最大 80,006 B（≤80 KB） |
| 图片 | 407 个媒体文件（406 张正文图 + 封面），书内图最大约 1.2 M 像素 |
| 字体 | 不内嵌，交给阅读器 |
| 体积 | 13.18 MB |

## 转换时踩到并解决的坑

1. **段落还原不能用左边界**。本书大量悬挂缩进编号项（首行 x=75、续行 x=111），按 x 对齐会把 800+ 段切碎。改成按行距判定（13.8pt 同段 / 27.6pt 新段）。
2. **一行里有一个内联加粗词就会切断整段**。段落强调级别按「字符数多数票」判定，而不是「存在加粗即加粗」。
3. **项目符号是独立文本对象**。Courier 的 `o`、Symbol 的 `\uf0b7` 与正文同一行但 y 差 1–2pt，不先折叠进条目首行就会被排序成「…in the o sample.」。
4. **只抽栅格图会丢掉 29 页图表**。K 线示意图、对比表全是矢量绘制，需按区域栅格化。
5. **8 页双栏表在图与文字上互相压字**（源 PDF 的问题，poppler 独立渲染复现）。改为逐行重建：文字抽成真段落，图形先 redaction 抹字再按行裁剪。
6. **引号码位错乱**。Nitro 把 `U+201F` 当撇号用（本书 1072 处），需按码位修正为 `’`。

## 平台侧规范

Apple Books 有完整官方规范（[Apple Books Asset Guide 5.3.1](https://help.apple.com/itc/booksassetguide/en.lproj/static.html)），微信读书没有公开的技术规范。两边的可确证事实、证据强度与出处都整理在 [`reference/PLATFORM-EPUB-GUIDANCE.md`](reference/PLATFORM-EPUB-GUIDANCE.md)。

## 已知取舍

- 544 等表单位保留为整页图片：那是空白待填模板，重排没有意义。
- 原 PDF 第 3–8 页目录的页码本身是错的（每卷从 15 重新计数），已丢弃并重建目录。
- 内置封面源于 PDF 内嵌的 492×636 原生图（上下补底色至 492×711 以适配微信读书 128:185 书架比例），短边低于 Apple 对「营销封面」建议的 1400px；该图本身上限如此，放大无意义。
