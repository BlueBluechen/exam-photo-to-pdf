#!/usr/bin/env python3
"""Wrap page images into a print-ready PDF with lossless (Flate) image data.

Usage:
  python3 make_pdf.py --images build/student/*.png --output 学生版.pdf \
      --size a4 --orientation auto --title "标题"

Pillow's PDF writer re-encodes pages as JPEG; this does not.
Refuses aspect mismatches above 1% so pages are not silently squeezed.
"""
import argparse
import glob
import os
import re
import zlib
import numpy as np
from PIL import Image

PAPER = {"a4": (210.0, 297.0), "letter": (215.9, 279.4), "b3": (353.0, 500.0), "b5": (176.0, 250.0)}


def natural(paths):
    key = lambda s: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]
    return sorted(paths, key=key)


def utf16_hex(s):
    return "<FEFF" + s.encode("utf-16-be").hex().upper() + ">"


def build(paths, out, title, w_mm, h_mm):
    W, H = w_mm / 25.4 * 72.0, h_mm / 25.4 * 72.0
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>"}
    kids, nid = [], 3
    for p in paths:
        im = Image.open(p)
        cs = b"/DeviceGray" if im.mode == "L" else b"/DeviceRGB"
        comp = zlib.compress(im.tobytes(), 9)
        img_id, page_id, cont_id = nid, nid + 1, nid + 2
        nid += 3
        objs[img_id] = (
            b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s "
            b"/BitsPerComponent 8 /Filter /FlateDecode /Interpolate false /Length %d >>\nstream\n"
            % (im.width, im.height, cs, len(comp))
        ) + comp + b"\nendstream"
        content = ("q %.4f 0 0 %.4f 0 0 cm /Im0 Do Q" % (W, H)).encode()
        objs[cont_id] = b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"
        objs[page_id] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.4f %.4f] "
            b"/Resources << /XObject << /Im0 %d 0 R >> >> /Contents %d 0 R >>"
            % (W, H, img_id, cont_id)
        )
        kids.append(b"%d 0 R" % page_id)
    objs[2] = b"<< /Type /Pages /Count %d /Kids [%s] >>" % (len(kids), b" ".join(kids))
    info_id = nid
    objs[info_id] = b"<< /Title " + utf16_hex(title).encode() + b" /Producer (exam-photo-to-pdf) >>"

    buf = bytearray(b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n")
    off = {}
    for i in sorted(objs):
        off[i] = len(buf)
        buf += b"%d 0 obj\n" % i + objs[i] + b"\nendobj\n"
    xref = len(buf)
    count = info_id + 1
    buf += b"xref\n0 %d\n0000000000 65535 f \n" % count
    for i in range(1, count):
        buf += b"%010d 00000 n \n" % off[i] if i in off else b"0000000000 65535 f \n"
    buf += (b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (count, info_id, xref))
    with open(out, "wb") as f:
        f.write(buf)
    return len(buf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="+", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--size", default="a4")
    ap.add_argument("--orientation", default="auto", choices=["auto", "landscape", "portrait"])
    ap.add_argument("--title", default="")
    a = ap.parse_args()

    if a.size in PAPER:
        short, long_ = PAPER[a.size]
    else:
        m = re.fullmatch(r"([\d.]+)x([\d.]+)", a.size)
        if not m:
            raise SystemExit("--size 需为 a4/letter/b5 或 宽x高(mm)")
        short, long_ = sorted(float(v) for v in m.groups())

    paths = natural([p for pat in a.images for p in glob.glob(pat)])
    first = Image.open(paths[0])
    landscape = first.width >= first.height
    if a.orientation == "portrait":
        landscape = False
    elif a.orientation == "landscape":
        landscape = True
    w_mm, h_mm = (long_, short) if landscape else (short, long_)

    for p in paths:
        im = Image.open(p)
        err = (im.width / im.height) / (w_mm / h_mm) - 1
        if abs(err) > 0.01:
            raise SystemExit(f"{p} 长宽比与页面相差 {err*100:+.2f}%，请在 clean.py 中裁切或改用 --size")

    size = build(paths, a.output, a.title, w_mm, h_mm)
    print(f"{a.output}  {len(paths)} 页  {w_mm:.1f}x{h_mm:.1f} mm  {size/1024:.0f} KB  无损 Flate")


if __name__ == "__main__":
    main()
