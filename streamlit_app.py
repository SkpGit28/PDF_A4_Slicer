# top of streamlit_app.py
try:
    import fitz  # PyMuPDF
except ModuleNotFoundError:
    import pymupdf as fitz  # fallback name on some environments

import streamlit as st
import math
from io import BytesIO
import streamlit as st
import fitz  # PyMuPDF
import math
from io import BytesIO

A4_W, A4_H = 595, 842  # portrait A4 in points

def slice_pdf_to_a4_portrait(pdf_bytes: bytes, scale: float, remove_blanks: bool, page_index: int):
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    if len(src) == 0:
        src.close()
        raise ValueError("PDF has no pages.")

    page_index = max(0, min(page_index, len(src) - 1))
    spage = src[page_index]
    SRC_W, SRC_H = spage.rect.width, spage.rect.height

    tile_w = A4_W / scale
    tile_h = A4_H / scale
    cols = math.ceil(SRC_W / tile_w)
    rows = math.ceil(SRC_H / tile_h)

    # safety guard for free tier
    if rows * cols > 800:
        src.close()
        raise ValueError(f"This scale would create {rows*cols} pages (>800). Lower the scale.")

    out = fitz.open()
    total = rows * cols
    made = 0
    prog = st.progress(0, text="Slicing…")

    for r in range(rows):
        top = r * tile_h
        bottom = min(top + tile_h, SRC_H)
        if bottom - top < 1:
            continue
        for c in range(cols):
            left  = c * tile_w
            right = min(left + tile_w, SRC_W)
            if right - left < 1:
                continue

            clip = fitz.Rect(left, top, right, bottom)

            dpage = out.new_page(-1, width=A4_W, height=A4_H)
            dpage.show_pdf_page(
                fitz.Rect(0, 0, A4_W, A4_H),
                spage.parent,
                spage.number,
                clip=clip,
                keep_proportion=False
            )

            if remove_blanks:
                tiny = dpage.get_pixmap(matrix=fitz.Matrix(0.1, 0.1),
                                        colorspace=fitz.csGRAY, alpha=False)
                if all(b == 255 for b in tiny.samples):
                    out.delete_page(-1)

            made += 1
            if made % 5 == 0 or made == total:
                prog.progress(min(made / total, 1.0), text=f"Slicing… {made}/{total}")

    if out.page_count == 0:
        src.close(); out.close()
        raise ValueError("All slices appeared blank. Try a different scale or page.")

    buf = BytesIO()
    out.save(buf)
    buf.seek(0)
    out.close()
    src.close()
    return buf, rows, cols, out.page_count

st.set_page_config(page_title="Tall PDF → A4 (Portrait)", page_icon="📄", layout="centered")

st.title("Tall PDF → A4 Slices (Portrait, Vector)")
st.caption("Vector-preserving tiling. Set a larger **Scale** for bigger text (more pages).")

# (optional) show Python to confirm runtime pin worked
import sys
st.sidebar.info(f"Python: {sys.version.split()[0]}")

uploaded = st.file_uploader("Upload a single tall-page PDF", type=["pdf"])
scale = st.slider("Scale (bigger = larger text)", min_value=0.40, max_value=1.00, value=0.80, step=0.05)
remove_blanks = st.checkbox("Remove blank pages", value=True)
page_number = st.number_input("Page number (if your PDF has multiple pages)", min_value=1, value=1, step=1)

if st.button("Create A4 PDF", type="primary") and uploaded:
    try:
        pdf_bytes = uploaded.read()
        buf, rows, cols, out_pages = slice_pdf_to_a4_portrait(
            pdf_bytes, float(scale), bool(remove_blanks), int(page_number) - 1
        )
        st.success(f"Done! Grid: {rows} rows × {cols} cols · Output pages: {out_pages}")
        st.download_button("Download A4 PDF", data=buf.getvalue(),
                           file_name="sliced_a4_portrait.pdf", mime="application/pdf")
    except Exception as e:
        st.error(f"Error: {e}")
