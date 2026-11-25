#!/usr/bin/env python3
"""Compare a generated PDF against the original page images, pixel by pixel.

Usage:
  python3 verify.py --pdf 学生版.pdf --sources 1.jpg 2.jpg 3.jpg 4.jpg \
      --workdir build/student --answers auto --outdir build/diff

Checks: lossless container, content bbox, ink structure, erased-strip residue.
Exit code 1 if any hard check fails.
"""
import argparse
import os
import re
import zlib
import numpy as np
from PIL import Image


def to_L(a):
    return a.astype(float) if a.ndim == 2 else (0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2])


def pdf_pages(path):
    d = open(path, "rb").read()
    out = []
    for m in re.finditer(rb"/Width (\d+) /Height (\d+) /ColorSpace /(\w+) /BitsPerComponent 8 "
                         rb"/Filter /FlateDecode .*?/Length (\d+) >>\nstream\n", d, re.S):
        w, h, cs, n = int(m.group(1)), int(m.group(2)), m.group(3).decode(), int(m.group(4))
        raw = zlib.decompress(d[m.end():m.end() + n])
        out.append(np.frombuffer(raw, np.uint8).reshape((h, w) if cs == "DeviceGray" else (h, w, 3)))
    return out


def bands(idx, gap):
    if len(idx) == 0:
        return []
    out, cur = [], [idx[0]]
    for v in idx[1:]:
        if v - cur[-1] <= gap:
            cur.append(v)
        else:
            out.append((cur[0], cur[-1]))
            cur = [v]
    out.append((cur[0], cur[-1]))
    return out


def colour_boxes(a, min_area=200):
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    m = (r - np.maximum(g, b)) > 18
    out = []
    for y0, y1 in bands(np.nonzero(m.any(1))[0], 6):
        for x0, x1 in bands(np.nonzero(m[y0:y1 + 1].any(0))[0], 26):
            if m[y0:y1 + 1, x0:x1 + 1].sum() >= min_area:
                out.append((x0, y0, x1, y1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--sources", nargs="+", required=True)
    ap.add_argument("--workdir", required=True, help="clean.py 的输出目录")
    ap.add_argument("--answers", default="auto", choices=["auto", "strip", "keep"],
                    help="strip=彩色答案应被抹净；keep=应保留；auto=按处理图自动判断")
    ap.add_argument("--outdir", default="")
    a = ap.parse_args()

    pages = pdf_pages(a.pdf)
    ok = True
    print(f"PDF 页数 {len(pages)}，源图 {len(a.sources)}")
    if len(pages) != len(a.sources):
        print("!! 页数不一致")
        ok = False

    for i, (pg, src) in enumerate(zip(pages, a.sources), 1):
        proc = os.path.join(a.workdir, f"page_{i}.png")
        orig = np.asarray(Image.open(src).convert("RGB")).astype(int)
        oL = to_L(orig)
        nL = to_L(pg)

        basis = proc if os.path.exists(proc) else None
        same = int(np.abs(nL - to_L(np.asarray(Image.open(basis)))).max()) if basis else None

        boxes = colour_boxes(orig)
        kept_colour = [int(((pg[y0:y1 + 1, x0:x1 + 1, 0] - np.maximum(pg[y0:y1 + 1, x0:x1 + 1, 1],
                                                                     pg[y0:y1 + 1, x0:x1 + 1, 2])) > 3).sum())
                       for x0, y0, x1, y1 in boxes] if pg.ndim == 3 else []
        mode = a.answers
        if mode == "auto":
            mode = "keep" if any(v > 0 for v in kept_colour) else "strip"

        keep = np.ones_like(oL, bool)
        if mode == "strip":
            for x0, y0, x1, y1 in boxes:
                keep[max(0, y0 - 9):y1 + 10, max(0, x0 - 56):x1 + 22] = False
        oi, ni = (oL < 128) & keep, (nL < 128) & keep
        iou = (oi & ni).sum() / max(1, (oi | ni).sum())
        corr = float(np.corrcoef(oi.sum(1), ni.sum(1))[0, 1])

        ys, xs = np.nonzero(nL < 128)
        ys0, xs0 = np.nonzero(oL < 128)
        bbox_same = (xs.min() == xs0.min() and xs.max() == xs0.max()
                     and ys.min() == ys0.min() and ys.max() == ys0.max())

        resid = [int((nL[max(0, y0 - 8):y1 + 9, max(0, x0 - 20):x1 + 20] < 200).sum())
                 for x0, y0, x1, y1 in boxes]

        # 过量抹除：源图中性黑字在成图中消失，且不在彩色答案簇内
        neutral = (orig.max(2) - orig.min(2)) < 25
        lost = (oL < 110) & neutral & (nL >= 150)
        for x0, y0, x1, y1 in boxes:
            lost[max(0, y0 - 9):y1 + 10, max(0, x0 - 60):x1 + 22] = False
        lost_clusters = []
        for y0, y1 in bands(np.nonzero(lost.any(1))[0], 4):
            for x0, x1 in bands(np.nonzero(lost[y0:y1 + 1].any(0))[0], 12):
                area = int(lost[y0:y1 + 1, x0:x1 + 1].sum())
                if area >= 20:
                    lost_clusters.append((area, x0, y0, x1, y1))

        print(f"p{i}: 与处理图最大差 {same} | bbox 一致 {bbox_same} | IoU {iou:.4f} 行相关 {corr:.4f} | 模式 {mode}")
        if boxes and mode == "strip":
            print(f"    抹除区残留 {resid}")
        if boxes and mode == "keep":
            print(f"    保留彩色 {kept_colour}")
            if any(v == 0 for v in kept_colour):
                print("    !! 有答案块丢失颜色")
        if lost_clusters:
            print(f"    !! 疑似误删正文 {len(lost_clusters)} 处：" +
                  ", ".join(f"{c[0]}px@x{c[1]}-{c[3]},y{c[2]}-{c[4]}" for c in lost_clusters[:5]))
        hard = (same == 0) and bbox_same and corr >= 0.99 and not lost_clusters
        if mode == "strip":
            hard = hard and all(v == 0 for v in resid)
        elif kept_colour:
            hard = hard and all(v > 0 for v in kept_colour)
        if not hard:
            ok = False
            print("    !! 未通过")

        if a.outdir:
            os.makedirs(a.outdir, exist_ok=True)
            vis = np.dstack([np.full_like(nL, 255, dtype=np.uint8)] * 3)
            vis[ni] = [0, 0, 0]
            vis[np.abs(oL - nL) > 60] = [220, 0, 0]
            Image.fromarray(vis).save(os.path.join(a.outdir, f"diff_{i}.png"))

    print("结论：" + ("全部通过" if ok else "存在未通过项，需复查"))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
