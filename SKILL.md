---
name: exam-photo-to-pdf
description: Turns photos or screenshots of an exam paper or worksheet into a clean, printable A4 PDF — removes watermarks and printed answers, keeps the page exactly as it was laid out. Use when a teacher or parent has page images of a test paper and wants to print it or hand it out. Not for rewriting questions or editing PDF forms.
---

# Exam Photo to PDF

Phone photos of a test paper in, a printable A4 sheet out. Everything on the page stays where it was; watermarks and printed answer keys come off; the sheet prints at the size the original was designed for.

Three rules keep the result trustworthy: measure the page before deciding how to fix it, only remove what was clearly classified, and compare pixels afterwards so nothing is invented or lost.

## First, measure the page

Never assume "it's a phone photo, so I need perspective correction". Run the probe on every page first. Pages exported from a PDF viewer, scanned flatbeds, and screenshots need none of it, and applying deskew/warp to them only destroys quality.

```bash
python3 scripts/probe_pages.py 1.jpg 2.jpg 3.jpg 4.jpg
```

It reports per page: pixel size, aspect vs A4, effective dpi at full-page print, residual rotation, ink bounding box in mm, background colour, and the colour-cluster layout of saturated pixels. Read those numbers, then choose a route.

Decision inputs that matter:

| Signal | Meaning for the pipeline |
|---|---|
| Effective dpi ≥ 300 | Keep as is, no sharpening needed |
| Effective dpi 140–300, screen-rendered text | Native resolution + levels + light unsharp; never upscale |
| Aspect within 0.3% of A4 | Place full-bleed on A4, no crop, no scale |
| Residual rotation > 0.3° | Deskew; below that, ignore |
| Ink bbox touches an edge | Content is cut off — tell the user before proceeding |
| Light uniform tint covering the whole page | Watermark/label overlay, removable by a white-point lift |
| Saturated red/blue clusters | Printed answer key or handwriting — must be classified, not blindly erased |

## Pick one of three routes

- **A 保真 / faithful** — one image per page, no retouching. Only for archiving or forwarding. Zero content risk, keeps watermarks and answer keys.
- **B 净化 / cleaned** — white-point lift, optional watermark/answer removal, light sharpening, lossless PDF. This is the default for anything that will be printed and used.
- **C 重排 / re-typeset** — OCR and rebuild as native text. Only when the result must be editable or reused long-term; it costs manual proofreading of every formula and figure, so do not pick it for a one-off print.

State the route and why in one line, then execute. Do not silently pick C.

## The cleaning pass

1. **White-point lift.** Map the paper tint to pure white. A screen-rendered page's overlay often sits 10–20 levels below white; scaling by `255/236` removes it while leaving black ink at black. Measure the actual background colour from the probe instead of hard-coding.
2. **Remove the overlay/watermark** — only when the user wants a clean sheet. Same white-point operation handles light tints; heavy watermarks need a mask.
3. **Remove answer/annotation colour** — see the classification rule below. This is where past runs broke sheets.
4. **Sharpen lightly.** `UnsharpMask(radius≈1.2, percent 30–55, threshold 2)`. More than 60% fattens strokes and visibly darkens the page.
5. **Convert to grayscale** for the student/consume copy when only black ink remains; keep colour for the answer-key copy.
6. **Embed losslessly** (see packaging).

```bash
# cleaned student copy, answers removed
python3 scripts/clean.py --inputs 1.jpg 2.jpg 3.jpg 4.jpg --outdir build/student \
    --drop-red --gray --white-point 236 --sharpen 55

# answer-key copy, red answers kept
python3 scripts/clean.py --inputs 1.jpg 2.jpg 3.jpg 4.jpg --outdir build/answer \
    --white-point 236 --sharpen 55
```

### Colour-removal classification rule (the part that breaks silently)

A red answer block and a red mark that belongs to the artwork look identical to a colour filter. Separate them by **size**, then by **layout geometry**:

- Cluster area ≥ ~200 px at 150 dpi → text, removes cleanly.
- Cluster area < ~100 px, sitting on a line junction or a figure vertex → **graphic element, keep it**. Erasing it leaves gaps at every vertex of every diagram.
- Answers sit at the end of a sentence, preceded by a whitespace gap of roughly one character. Erasing by colour threshold alone leaves the thin `（` surviving, because JPEG chroma subsampling turns a hairline stroke into neutral grey that no colour threshold catches. **Use the gap**: scan left from the answer cluster to the first ≥8-column blank run, then clear the whole strip from there.
- Scan that gap on the **cluster's own text rows only**. If the blank band is an answer underline, it bridges the gap and the scan runs back through the preceding sentence, deleting real content. This failure is invisible in a thumbnail — only a "source ink that vanished" check catches it.

`clean.py` carries both rules. Look at the output anyway — the script cannot know that a stray red dot was a vertex.

## Packaging: lossless, or the work is wasted

Pillow's `save(..., "PDF")` re-encodes every page as JPEG (DCTDecode) at default quality, so a page that took work to clean gets compressed again. Use `scripts/make_pdf.py`, which embeds Flate-compressed image data and sets the MediaBox to the exact physical page size.

```bash
python3 scripts/make_pdf.py --images build/student/*.png \
    --output 学生版.pdf --size a4 --orientation auto --title "标题"
```

- Page size comes from `--size`; `--orientation auto` picks the one matching the image aspect and refuses a mismatch above 1%.
- Never resample to 300 dpi. Upscaling a 155 dpi page adds bytes, not detail; print it at 100% instead. Say so explicitly if the user expects "300 dpi".

## Then check it pixel by pixel

```bash
python3 scripts/verify.py --pdf 学生版.pdf --sources 1.jpg 2.jpg 3.jpg 4.jpg \
    --workdir build/student --answers auto
```

`--answers auto` decides per copy whether colour should have been stripped or kept; force `strip` / `keep` when the detection could be fooled.

It decodes the images back out of the PDF and checks:

| Check | Pass condition |
|---|---|
| PDF image vs processing output | max diff 0 (proves the container is lossless) |
| Content bbox vs source | identical, no crop and no shift |
| Ink IoU / row-profile correlation | correlation ≥ 0.99 (IoU alone drops on 1–2 px strokes after sharpening) |
| Residual ink in erased strips | 0 pixels |
| Source ink that vanished | no cluster ≥ 20 px outside the colour areas — catches over-erasure |
| Answer-key copy retains colour | every answer block still has coloured pixels |
| Page geometry | exact mm size, expected page count, Flate only |

Then look at the rendered pages once. Automated diffing cannot judge whether a figure still reads correctly.

Report a failure honestly instead of shipping it. If a fix changes an earlier claim, say what changed.

## Delivering the file

- Name files by content and role: `<标题>_学生版.pdf`, `<标题>_答案版.pdf`. Two copies is usually right: a clean one to work on, an annotated one to check against.
- Tell the user the print settings that actually matter: paper size, orientation, and **scale 100% / actual size**, with fit-to-page turned off, because driver-side scaling resamples a second time.
- Report page count, physical size, effective dpi, and the checks that passed. Do not claim "300 dpi" when the source cannot support it.
- Keep intermediates in a temp directory; deliver only the PDFs.

## Common mistakes

- Erasing red before checking whether the artwork uses red.
- Judging removal at thumbnail scale; thin leftover parentheses and grey ghosts are only visible at 2–3×.
- Trusting the eye instead of decoding the PDF and comparing pixels.
- Cropping to the ink bbox "for a tighter margin" — it shifts everything and can clip the last line.
- Re-running the PDF writer after editing only the images, then comparing against a stale file.
- Trusting "残留为 0" alone: it proves nothing was left over, not that nothing was eaten. Check vanished ink too.
