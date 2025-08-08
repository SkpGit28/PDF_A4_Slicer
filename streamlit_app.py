import streamlit as st
import math
from io import BytesIO
from pypdf import PdfReader, PdfWriter, Transformation

A4_W, A4_H = 595, 842  # portrait A4 in points
HARD_PAGE_CAP = 800    # safety to avoid runaway jobs on free tier


def slice_pdf_to_a4_portrait(pdf_bytes: bytes, scale: float, page_index: int) -> BytesIO:
    reader = PdfReader(BytesIO(pdf_bytes))
    if len(reader.pages) == 0:
        raise ValueError("PDF has no pages.")

    page_index = max(0, min(page_index, len(reader.pages) - 1))
    src = reader.pages[page_index]

    # Source size
    src_w = float(src.mediabox.width)
    src_h = float(src.mediabox.height)

    # How much of the source fits on one A4 page at this scale?
    tile_w = A4_W / scale
    tile_h = A4_H / scale
    cols = math.ceil(src_w / tile_w)
    rows = math.ceil(src_h / tile_h)

    total_tiles = rows * cols
    if total_tiles > HARD_PAGE_CAP:
        raise ValueError(
            f"This scale would create {total_tiles} pages (> {HARD_PAGE_CAP}). "
            "Lower the scale (slider) and try again."
        )

    writer = PdfWriter()

    # Custom loader UI
    progress = st.progress(0, text="Starting…")
    made = 0

    with st.status("Slicing PDF…", expanded=True) as status:
        st.write(f"Source size: {int(src_w)} × {int(src_h)} pt")
        st.write(f"Grid: {rows} rows × {cols} cols (max {HARD_PAGE_CAP})")
        status.update(label="Slicing pages…", state="running")

        # Build tiles row-by-row from top (our mental model) to bottom.
        # Convert to PDF bottom-left coords:
        # y_bottom_bl = src_h - (top + tile_h)
        for r in range(rows):
            top_tl = r * tile_h
            bottom_tl = min(top_tl + tile_h, src_h)
            if bottom_tl - top_tl < 1:
                continue
            y_bottom_bl = src_h - bottom_tl

            for c in range(cols):
                left = c * tile_w
                right = min(left + tile_w, src_w)
                if right - left < 1:
                    continue

                # Create A4 page
                out_page = writer.add_blank_page(width=A4_W, height=A4_H)

                # Transform: scale, then translate by *scaled* offsets
                t = (
                    Transformation()
                    .scale(scale)
                    .translate(tx=-left * scale, ty=-y_bottom_bl * scale)
                )

                out_page.merge_transformed_page(src, t)

                made += 1
                if made % 5 == 0 or made == total_tiles:
                    progress.progress(made / total_tiles, text=f"Slicing… {made}/{total_tiles}")

        status.update(label="Packaging PDF…", state="running")

    buf = BytesIO()
    writer.write(buf)
    buf.seek(0)
    progress.progress(1.0, text="Done")
    return buf, rows, cols, made


# ---------------- Streamlit UI ----------------
st.set_page_config(page_title="Tall PDF → A4 (Portrait)", page_icon="📄", layout="centered")
st.title("Tall PDF → A4 Slices (Portrait, Vector)")
st.caption("Vector-preserving tiling. Increase **Scale** for bigger text (more pages).")

uploaded = st.file_uploader("Upload a tall single-page PDF (or pick the page # below)", type=["pdf"])
scale = st.slider("Scale (bigger = larger text)", min_value=0.40, max_value=1.00, value=0.80, step=0.05)
page_number = st.number_input("Page number (if your PDF has multiple pages)", min_value=1, value=1, step=1)

# Disable the convert button until a file is uploaded
convert_disabled = uploaded is None
convert = st.button("Convert to A4 PDF", type="primary", disabled=convert_disabled)

# Show an estimate before conversion (if a file is uploaded)
if uploaded is not None:
    try:
        # Peek only minimal metadata to estimate grid
        pdf_bytes_peek = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded.read()
        reader_peek = PdfReader(BytesIO(pdf_bytes_peek))
        idx = max(0, min(page_number - 1, len(reader_peek.pages) - 1))
        src = reader_peek.pages[idx]
        src_w = float(src.mediabox.width)
        src_h = float(src.mediabox.height)
        tile_w = A4_W / scale
        tile_h = A4_H / scale
        cols_est = math.ceil(src_w / tile_w)
        rows_est = math.ceil(src_h / tile_h)
        total_est = rows_est * cols_est
        st.info(f"Estimated grid at current scale: {rows_est} rows × {cols_est} cols "
                f"(~{total_est} pages). Cap: {HARD_PAGE_CAP}")
    except Exception:
        pass  # Estimation is best-effort; we still handle errors during real run.

if convert and uploaded:
    try:
        # Get raw bytes safely (Streamlit can re-run; read once here)
        pdf_bytes = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded.read()

        buf, rows, cols, out_pages = slice_pdf_to_a4_portrait(
            pdf_bytes=pdf_bytes,
            scale=float(scale),
            page_index=int(page_number) - 1
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
