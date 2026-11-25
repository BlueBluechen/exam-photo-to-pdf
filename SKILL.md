---
name: exam-photo-to-pdf
description: 把手机拍的试卷照片转成能直接打印的 A4 PDF，去掉水印和印刷答案，题目与版式留在原位。老师、家长都能用。
---

# 试卷照片转可打印 PDF

手机拍的卷子，变成能直接打印的 A4。题目、选项、图形都在原来的位置，页边距也不动。

- 去水印
- 去印刷答案，图形上的红色标记保留
- 按原始比例排 A4，不拉伸、不裁切
- 无损导出，打印不糊、不重复压缩

## 用法

```bash
python3 scripts/probe_pages.py 1.jpg 2.jpg 3.jpg 4.jpg      # 先量：尺寸、清晰度、有没有歪
python3 scripts/clean.py --inputs 1.jpg 2.jpg 3.jpg 4.jpg \
    --outdir build/student --drop-red --gray                # 去水印、去答案，学生版
python3 scripts/make_pdf.py --images "build/student/*.png" \
    --output 学生版.pdf --size a4                           # 合成 A4 PDF
python3 scripts/verify.py --pdf 学生版.pdf --sources 1.jpg 2.jpg 3.jpg 4.jpg \
    --workdir build/student                                 # 逐像素核对
```

只要答案版：`clean.py` 去掉 `--drop-red --gray`，`make_pdf.py` 指向 `build/answer`。

## 规则

- 先量再改。155 dpi 的图不要放大到 300，也不要硬做透视矫正——量完没歪就别碰。
- 面积 ≥200 px 的彩色块是答案；<100 px 的常常是图形顶点，删了图上会缺口。
- 抹答案从空白间隙开始，只在该行扫描。扫到答案下划线会把前一句一起带走。
- 白点按实测底色抬，不要写死。
- 锐化 30–55%，超过 60% 字会变粗、整页发黑。

## 交付

- 两份：学生版去答案、转灰度；答案版留红色，给家长对照。
- 打印设 100% 实际大小，关掉「适应页面」，否则驱动会再插值一次。
- 报页数、尺寸、有效 dpi，以及 `verify.py` 过了哪几项。源图只有 155 dpi，就别说是 300。
