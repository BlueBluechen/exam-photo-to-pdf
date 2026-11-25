#!/usr/bin/env python3
"""Measure page images before choosing a processing route.

Usage: python3 inspect.py 1.jpg 2.jpg [--size a4]
Reports size, effective dpi at full-page print, residual rotation, ink box,
background colour, and saturated-colour clusters (printed answers / handwriting).
"""
import sys
import numpy as np
from PIL import Image

PAPER = {"a4": (210.0, 297.0), "letter": (215.9, 279.4), "b5": (176.0, 250.0)}


def to_L(a):
    if a.ndim == 2:
        return a.astype(float)
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


def skew_angle(gray, span=3.0, step=0.25):
    """Max row-projection variance = best baseline alignment."""
    im = Image.fromarray(gray.astype(np.uint8))
    if im.width > 700:
        im = im.resize((700, int(im.height * 700 / im.width)), Image.BILINEAR)
    best, best_v = 0.0, -1.0
    a = -span
    while a <= span + 1e-9:
        r = np.asarray(im.rotate(a, resample=Image.BILINEAR, fillcolor=255)).astype(float)
        v = ((255.0 - r).sum(1)).var()
        if v > best_v:
            best, best_v = a, v
        a += step
    return best


def clusters(mask, gap_y=5, gap_x=26):
    boxes = []
    for y0, y1 in bands(np.nonzero(mask.any(1))[0], gap_y):
        for x0, x1 in bands(np.nonzero(mask[y0:y1 + 1].any(0))[0], gap_x):
            boxes.append((int(mask[y0:y1 + 1, x0:x1 + 1].sum()), x0, y0, x1, y1))
    return sorted(boxes, reverse=True)


def inspect(path, paper=(210.0, 297.0)):
    im = Image.open(path)
    a = np.asarray(im.convert("RGB")).astype(int)
    h, w = a.shape[:2]
    L = to_L(a)
    long_mm, short_mm = paper[1], paper[0]
    # orientation matched to the image
    page_mm = (long_mm, short_mm) if w >= h else (short_mm, long_mm)
    dpi = w / (page_mm[0] / 25.4)
    want = page_mm[0] / page_mm[1]
    aspect_err = (w / h / want - 1) * 100

    ink = L < 128
    ys, xs = np.nonzero(ink)
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())) if len(xs) else None
    margins = None
    if bbox:
        margins = tuple(round(v / dpi * 25.4, 1) for v in (bbox[0], bbox[1], w - bbox[2], h - bbox[3]))

    bg = a[(L > 230)]
    bg_mode = tuple(int(v) for v in np.median(bg, 0)) if len(bg) else None

    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    mx, mn = a.max(2), a.min(2)
    sat = (mx - mn) > 40
    red = sat & (r - np.maximum(g, b) > 25)
    blue = sat & (b - np.maximum(r, g) > 25)
    other = sat & ~red & ~blue

    print(f"\n== {path}")
    print(f"   {w}x{h} px  mode={im.mode}  |  A4 {'横向' if w >= h else '纵向'} "
          f"有效 {dpi:.0f} dpi  |  长宽比误差 {aspect_err:+.2f}%")
    print(f"   残余旋转 {skew_angle(L):+.2f}°  |  背景色 {bg_mode}")
    if bbox:
        print(f"   墨迹 bbox x{bbox[0]}-{bbox[2]} y{bbox[1]}-{bbox[3]}  "
              f"页边距(左/上/右/下) {margins} mm")
    for name, m in (("红", red), ("蓝", blue), ("其他彩", other)):
        if m.sum() > 30:
            cs = clusters(m)
            small = [c for c in cs if c[0] < 200]
            print(f"   {name}色像素 {int(m.sum())}  色块 {len(cs)} 个  "
                  f"最大 {cs[0][0]}px @x{cs[0][1]}-{cs[0][3]} y{cs[0][2]}-{cs[0][4]}  "
                  f"| 小于200px 的 {len(small)} 个(可能是图形/手写笔迹)")
    return dict(w=w, h=h, dpi=dpi, aspect_err=aspect_err, bbox=bbox)


def main():
    args = sys.argv[1:]
    paper = PAPER["a4"]
    if "--size" in args:
        i = args.index("--size")
        paper = PAPER.get(args[i + 1], paper)
        args = args[:i] + args[i + 2:]
    if not args:
        print(__doc__)
        return
    for p in args:
        inspect(p, paper)


if __name__ == "__main__":
    main()
