#!/usr/bin/env python3
"""Clean page images for printing: white-point lift, optional colour-ink removal,
light sharpening, optional grayscale.

Usage:
  python3 clean.py --inputs 1.jpg 2.jpg --outdir build/student --drop-red --gray
  python3 clean.py --inputs 1.jpg 2.jpg --outdir build/answer --white-point 236

Colour-ink removal keeps small coloured clusters (figure vertices, tick marks)
and only erases text-sized ones; it clears by layout gap, not by colour alone,
so thin brackets do not survive as grey ghosts.
"""
import argparse
import os
import numpy as np
from PIL import Image, ImageFilter


def to_L(a):
    return 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]


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


def colour_boxes(a, chan, min_area, gap_y=6, gap_x=26):
    """Clusters of a given hue, split into text-sized (>= min_area) and small."""
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    if chan == "red":
        m = (r - np.maximum(g, b)) > 18
    elif chan == "blue":
        m = (b - np.maximum(r, g)) > 18
    else:  # any saturated colour
        m = (a.max(2) - a.min(2)) > 40
    text, small = [], []
    for y0, y1 in bands(np.nonzero(m.any(1))[0], gap_y):
        for x0, x1 in bands(np.nonzero(m[y0:y1 + 1].any(0))[0], gap_x):
            area = int(m[y0:y1 + 1, x0:x1 + 1].sum())
            (text if area >= min_area else small).append((x0, y0, x1, y1, area))
    return text, small


def strip_start(L, x0, y0, y1, gap, limit=80):
    """Walk left from a cluster to the first blank run of `gap` columns.

    Only the cluster's own text rows are inspected: including rows below would
    let a long answer underline bridge the blank gap, and the scan would run
    back through the sentence that precedes it.
    """
    band = (L[y0:y1 + 1] < 245).any(0)
    x, run = x0, 0
    while x > 0 and run < gap and x0 - x < limit:
        x -= 1
        run = run + 1 if not band[x] else 0
    return x + 1 if run >= gap else x0 - 10


def clean(path, outdir, args, idx):
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.int16)
    L = to_L(a.astype(float))
    removed = kept = 0

    if args.drop_colour != "none":
        text, small = colour_boxes(a, args.drop_colour, args.min_area)
        for x0, y0, x1, y1, area in text:
            xs = strip_start(L, x0, y0, y1, args.gap)
            X0, Y0 = max(0, xs), max(0, y0 - 7)
            X1, Y1 = min(a.shape[1], x1 + args.tail), min(a.shape[0], y1 + 8)
            reg = a[Y0:Y1, X0:X1]
            reg[L[Y0:Y1, X0:X1] < args.erase_below] = [255, 255, 255]
            a[Y0:Y1, X0:X1] = reg
            removed += 1
        kept = len(small)

    a = np.clip(a * (255.0 / args.white_point), 0, 255).astype(np.uint8)
    im = Image.fromarray(a)
    if args.gray:
        im = im.convert("L")
    if args.sharpen > 0:
        im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=int(args.sharpen), threshold=2))

    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"page_{idx}.png")
    im.save(out, optimize=True)
    if args.drop_colour != "none":
        print(f"  {os.path.basename(path)} -> {out}  抹除色块 {removed} 处，保留小色块 {kept} 处")
    else:
        print(f"  {os.path.basename(path)} -> {out}")
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inputs", nargs="+", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--drop-red", action="store_true", help="移除红色文字(如印刷答案)")
    p.add_argument("--drop-blue", action="store_true", help="移除蓝色笔迹")
    p.add_argument("--drop-any", action="store_true", help="移除任意高饱和彩色文字")
    p.add_argument("--min-area", type=int, default=200, help="视为文字的最小色块面积")
    p.add_argument("--gap", type=int, default=8, help="正文与彩色文字的空白列阈值")
    p.add_argument("--tail", type=int, default=16, help="向右扩展列数，覆盖右括号")
    p.add_argument("--erase-below", type=int, default=252, help="低于该亮度即抹白")
    p.add_argument("--white-point", type=float, default=236.0,
                   help="白点(0-255)：纸张底色高于此值即归白")
    p.add_argument("--sharpen", type=float, default=55.0, help="USM 强度百分比，0 关闭")
    p.add_argument("--gray", action="store_true")
    args = p.parse_args()

    args.drop_colour = "red" if args.drop_red else "blue" if args.drop_blue else "any" if args.drop_any else "none"
    outs = [clean(f, args.outdir, args, i) for i, f in enumerate(args.inputs, 1)]
    print(f"完成 {len(outs)} 页 -> {args.outdir}")


if __name__ == "__main__":
    main()
