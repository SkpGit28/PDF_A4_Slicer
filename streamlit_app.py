import streamlit as st
import fitz  # PyMuPDF
import math
from io import BytesIO

A4_W, A4_H = 595, 842  # portrait A4 in points

def slice_pdf_to_a4_portrait(pdf_bytes: bytes, scale: float, remove_blanks: bool):
    # open first page only (assumes a single very tall page)
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    if len(src) == 0:
        raise ValueError("PDF has no pages.")
    spage = src[0]
    SRC_W, SRC_H = spage.rect.width, spage.rect.height

    # how much of the source fits on one A4 page at this scale?
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

            # create a new A4 page and draw the clipped source area scaled to fill
            dpage = out.new_page(-1, width=A4_W, height=A4_H)
            dpage.show_pdf_page(fitz.Rect(0, 0, A4_W, A4_H),
                                src, 0, clip=clip, keep_proportion=False)

            if remove_blanks:
                # tiny greyscale render to detect blank pages cheaply
                pix = dpage.get_pixmap(matrix=fitz.Matrix(0.1, 0.1),
                                       colorspace=fitz.csGRAY, alpha=False)
                if all(b == 255 for b in pix.samples):  # all-white -> blank
                    out.delete_page(-1)  # remove page we just added

    buf = BytesIO()
    out.save(buf)
    out.close()
    src.close()
    buf.seek(0)
    return buf, rows, cols

st.set_page_config(page_title="Tall PDF → A4 (Portrait)", page_icon="📄", layout="centered")

st.title("Tall PDF → A4 Slices (Portrait)")
st.write("Upload a **single tall-page PDF** (e.g. exported ERD). "
         "Choose a **Scale** (bigger = larger text, more pages). "
         "We tile the page in both directions and return a **sharp vector PDF**.")

uploaded = st.file_uploader("Upload PDF", type=["pdf"])
scale = st.slider("Scale (bigger = larger text)", min_value=0.40, max_value=1.00, value=0.80, step=0.05)
remove_blanks = st.checkbox("Remove blank pages", value=True)

if st.button("Create A4 PDF") and uploaded:
    pdf_bytes = uploaded.read()
    with st.spinner("Slicing…"):
        try:
            result_buf, rows, cols = slice_pdf_to_a4_portrait(pdf_bytes, scale, remove_blanks)
        except Exception as e:
            st.error(f"Failed: {e}")
        else:
            st.success(f"Done! Grid: {rows} rows × {cols} cols.")
            st.download_button(
                label="Download A4 PDF",
                data=result_buf.getvalue(),
                file_name="sliced_a4_portrait.pdf",
                mime="application/pdf",
            )
            st.caption("Tip: Increase **Scale** if text looks small; expect more pages.")

st.markdown("---")
st.markdown("**Notes**")
st.markdown("- Keeps **portrait** orientation. "
            "If your PDF has multiple pages, only the **first** tall page is used.\n"
            "- Blank pages are removed via a quick greyscale check; set **Remove blank pages** off to keep every tile.")
