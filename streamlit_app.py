import gradio as gr
import fitz  # PyMuPDF
import math
from io import BytesIO

A4_W, A4_H = 595, 842  # A4 portrait in points

def slice_pdf(pdf_file, scale=0.80, remove_blanks=True, page_number=1):
    # read the uploaded file into memory
    data = pdf_file.read() if hasattr(pdf_file, "read") else open(pdf_file.name, "rb").read()
    src = fitz.open(stream=data, filetype="pdf")
    if len(src) == 0:
        raise ValueError("PDF has no pages.")

    # which page to slice (1-indexed in UI)
    idx = max(1, int(page_number)) - 1
    if idx >= len(src):
        idx = 0
    spage = src[idx]

    SRC_W, SRC_H = spage.rect.width, spage.rect.height

    # how much of the source fits one A4 page at this scale?
    # (portrait only, vector-preserving)
    tile_w = A4_W / scale
    tile_h = A4_H / scale
    cols = math.ceil(SRC_W / tile_w)
    rows = math.ceil(SRC_H / tile_h)

    out = fitz.open()

    for r in range(rows):
        top = r * tile_h
        bottom = min(top + tile_h, SRC_H)
        if bottom - top < 1:  # zero-height slice
            continue

        for c in range(cols):
            left  = c * tile_w
            right = min(left + tile_w, SRC_W)
            if right - left < 1:  # zero-width slice
                continue

            clip = fitz.Rect(left, top, right, bottom)

            # draw the clipped source area scaled to full A4 page
            dpage = out.new_page(-1, width=A4_W, height=A4_H)
            dpage.show_pdf_page(
                fitz.Rect(0, 0, A4_W, A4_H),
                src, idx,
                clip=clip,
                keep_proportion=False
            )

            if remove_blanks:
                # cheap blank-page detector (tiny greyscale render)
                tiny = dpage.get_pixmap(
                    matrix=fitz.Matrix(0.1, 0.1),
                    colorspace=fitz.csGRAY,
                    alpha=False
                )
                if all(b == 255 for b in tiny.samples):
                    out.delete_page(-1)

    buf = BytesIO()
    out.save(buf)
    out.close()
    src.close()
    buf.seek(0)
    return buf

with gr.Blocks(title="Tall PDF → A4 (Portrait, Vector)") as demo:
    gr.Markdown(
        "## Tall PDF → A4 Slices (Portrait)\n"
        "- Upload a **single tall-page PDF** (e.g., ERD export)\n"
        "- **Scale** = bigger value → larger text → more pages\n"
        "- Pages are **vector-preserved** (crisp print), blank tiles auto-removed\n"
    )

    with gr.Row():
        inp = gr.File(file_types=[".pdf"], label="Upload PDF")

    with gr.Row():
        scale = gr.Slider(0.40, 1.00, value=0.80, step=0.05, label="Scale (bigger = larger text)")
        page_number = gr.Number(value=1, precision=0, label="Page number (if your PDF has multiple pages)")

    rm_blank = gr.Checkbox(value=True, label="Remove blank pages")
    run = gr.Button("Create A4 PDF", variant="primary")
    out = gr.File(label="Download result")

    def _run(pdf, s, rm, pn):
        return slice_pdf(pdf, s, rm, pn)

    run.click(_run, [inp, scale, rm_blank, page_number], out)

if __name__ == "__main__":
    demo.launch()
