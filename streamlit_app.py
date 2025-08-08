import streamlit as st
import math
from io import BytesIO
from pypdf import PdfReader, PdfWriter, Transformation

A4_W, A4_H = 595, 842  # portrait A4 in points

def slice_pdf_to_a4_portrait(pdf_bytes: bytes, scale: float, remove_blanks: bool, page_index: int):
    reader = PdfReader(BytesIO(pdf_bytes))
    if len(reader.pages) == 0:
        raise ValueError("PDF has no pages.")

    page_index = max(0, min(page_index, len(reader.pages) - 1))
    src = reader.pages[page_index]

    # Source page size (points)
    src_w = float(src.mediabox.width)
    src_h = float(src.mediabox.height)

    # How much of the source fits on one A4 page at this scale?
    tile_w = A4_W / scale
    tile_h = A4_H / scale

    cols = math.ceil(src_w / tile_w)
    rows = math.ceil(src_h / tile_h)

    # Safety for the free tier
    if rows * cols > 800:
        raise ValueError(f"This scale would create {rows*cols} pages (>800). Lower the scale.")

    writer = PdfWriter()

    total = rows * cols
    made = 0
    prog = st.progress(0, text="Slicing…")

    for r in range(rows):
        top = r * tile_h
        bottom = min(top + tile_h, src_h)
        if bottom - top < 1:
            continue

        for c in range(cols):
            left = c * tile_w
            right = min(left + tile_w, src_w)
            if right - left < 1:
                continue

            # Create a blank A4 page
            out_page = writer.add_blank_page(width=A4_W, height=A4_H)

            # Transform original page:
            #  - translate by (-left, -top) to bring the tile to origin
            #  - then scale by 'scale' to fill A4
            #  In PDF matrix terms: [a 0 0 d e f] with a=d=scale and e,f = -left*scale, -top*scale
            t = Transformation(a=scale, d=scale, e=-left * scale, f=-top * scale)

            # Merge the transformed source page onto the blank page (vector-preserving)
            out_page.merge_transformed_page(src, t)

            # Optional "blank page" skip for truly empty tiles:
            # pypdf can't render to check pixels, but tiles with zero area are already skipped.
            # If you still see blanks, lower scale a notch (rare with ERD diagrams).

            made += 1
            if made % 5 == 0 or made == total:
                prog.progress(min(made / total, 1.0), text=f"Slicing… {made}/{total}")

    buf = BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf, rows, cols, len(writer.pages)

# ---------------- Streamlit UI ----------------
st.set_page_config(page_title="Tall PDF → A4 (Portrait)", page_icon="📄", layout="centered")
st.title("Tall PDF → A4 Slices (Portrait, Vector)")
st.caption("Vector-preserving tiling. Set a larger **Scale** for bigger text (more pages).")

uploaded = st.file_uploader("Upload a single tall-page PDF", type=["pdf"])
scale = st.slider("Scale (bigger = larger text)", min_value=0.40, max_value=1.00, value=0.80, step=0.05)
remove_blanks = st.checkbox("Remove blank pages (N/A for pypdf heuristic)", value=True, disabled=True)
page_number = st.number_input("Page number (if your PDF has multiple pages)", min_value=1, value=1, step=1)

if st.button("Create A4 PDF", type="primary") and uploaded:
    try:
        pdf_bytes = uploaded.read()
        buf, rows, cols, out_pages = slice_pdf_to_a4_portrait(
            pdf_bytes, float(scale), True, int(page_number) - 1
        )
        st.success(f"Done! Grid: {rows} rows × {cols} cols · Output pages: {out_pages}")
        st.download_button(
            "Download A4 PDF",
            data=buf.getvalue(),
            file_name="sliced_a4_portrait.pdf",
            mime="application/pdf"
        )
    except Exception as e:
        st.error(f"Error: {e}")
