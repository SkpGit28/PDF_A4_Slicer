import streamlit as st
import math
from io import BytesIO

# Try fast engine (PyMuPDF); fall back to pypdf if not present
try:
    import fitz  # PyMuPDF
    HAVE_FITZ = True
except Exception:
    HAVE_FITZ = False
    from pypdf import PdfReader, PdfWriter, Transformation

A4_W, A4_H = 595, 842   # portrait A4 points
HARD_PAGE_CAP = 800     # safety

# ---------- engines ----------
def slice_with_fitz(pdf_bytes: bytes, scale: float, page_index: int):
    doc = fitz.open("pdf", pdf_bytes)
    if doc.page_count == 0:
        doc.close()
        raise ValueError("PDF has no pages.")

    page_index = max(0, min(page_index, doc.page_count - 1))
    spage = doc[page_index]
    src_w, src_h = spage.rect.width, spage.rect.height

    tile_w = A4_W / scale
    tile_h = A4_H / scale
    cols = math.ceil(src_w / tile_w)
    rows = math.ceil(src_h / tile_h)

    total = rows * cols
    if total > HARD_PAGE_CAP:
        doc.close()
        raise ValueError(f"This scale would create {total} pages (> {HARD_PAGE_CAP}). Lower the scale.")

    dst = fitz.open()
    prog = st.progress(0, text="Slicing…")
    made = 0

    # render tree reuse (faster)
    dl = spage.get_displaylist()

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

            clip = fitz.Rect(left, top, right, bottom)

            dpage = dst.new_page(-1, width=A4_W, height=A4_H)
            dpage.show_pdf_page(fitz.Rect(0, 0, A4_W, A4_H),
                                doc, page_index, clip=clip, keep_proportion=False)

            # tiny grayscale render to drop truly blank tiles (rare)
            tiny = dpage.get_pixmap(matrix=fitz.Matrix(0.05, 0.05),
                                    colorspace=fitz.csGRAY, alpha=False)
            if all(b == 255 for b in tiny.samples):
                dst.delete_page(-1)
            made += 1
            if made % 5 == 0 or made == total:
                prog.progress(made / total, text=f"Slicing… {made}/{total}")

    # write to memory via temp file (most reliable)
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_path = tmp.name; tmp.close()
    dst.save(tmp_path)
    dst.close(); doc.close()
    data = open(tmp_path, "rb").read()
    os.remove(tmp_path)
    return BytesIO(data), rows, cols, len(fitz.open("pdf", data))

def slice_with_pypdf(pdf_bytes: bytes, scale: float, page_index: int):
    from pypdf import PdfReader, PdfWriter, Transformation
    reader = PdfReader(BytesIO(pdf_bytes))
    if len(reader.pages) == 0:
        raise ValueError("PDF has no pages.")
    page_index = max(0, min(page_index, len(reader.pages) - 1))
    src = reader.pages[page_index]

    src_w = float(src.mediabox.width)
    src_h = float(src.mediabox.height)

    tile_w = A4_W / scale
    tile_h = A4_H / scale
    cols = math.ceil(src_w / tile_w)
    rows = math.ceil(src_h / tile_h)

    total = rows * cols
    if total > HARD_PAGE_CAP:
        raise ValueError(f"This scale would create {total} pages (> {HARD_PAGE_CAP}). Lower the scale.")

    writer = PdfWriter()
    prog = st.progress(0, text="Slicing…")
    made = 0

    for r in range(rows):
        top_tl = r * tile_h
        bottom_tl = min(top_tl + tile_h, src_h)
        if bottom_tl - top_tl < 1:
            continue
        y_bottom_bl = src_h - bottom_tl  # convert to PDF bottom-left

        for c in range(cols):
            left = c * tile_w
            right = min(left + tile_w, src_w)
            if right - left < 1:
                continue

            out_page = writer.add_blank_page(width=A4_W, height=A4_H)
            t = (Transformation().scale(scale)
                               .translate(tx=-left * scale, ty=-y_bottom_bl * scale))
            out_page.merge_transformed_page(src, t)

            made += 1
            if made % 5 == 0 or made == total:
                prog.progress(made / total, text=f"Slicing… {made}/{total}")

    buf = BytesIO()
    writer.write(buf); buf.seek(0)
    return buf, rows, cols, len(writer.pages)

# ---------- UI ----------
st.set_page_config(page_title="Tall PDF → A4 (Portrait)", page_icon="📄", layout="centered")
st.title("Tall PDF → A4 Slices (Portrait, Vector)")

engine_name = "PyMuPDF (fast)" if HAVE_FITZ else "pypdf (fallback, slower)"
st.caption(f"Engine: **{engine_name}** · Larger **Scale** = bigger text = more pages.")

uploaded = st.file_uploader("Upload a tall single-page PDF (or pick a page # below)", type=["pdf"])
scale = st.slider("Scale", min_value=0.40, max_value=1.00, value=0.80, step=0.05)
page_number = st.number_input("Page number (if your PDF has multiple pages)", min_value=1, value=1, step=1)

# Estimate grid/pages once a file is uploaded
if uploaded is not None:
    try:
        b = uploaded.getvalue()
        if HAVE_FITZ:
            import fitz
            d = fitz.open("pdf", b); p = d[max(0, min(page_number-1, d.page_count-1))]
            w, h = p.rect.width, p.rect.height; d.close()
        else:
            from pypdf import PdfReader
            r = PdfReader(BytesIO(b)); p = r.pages[max(0, min(page_number-1, len(r.pages)-1))]
            w, h = float(p.mediabox.width), float(p.mediabox.height)
        cols_est = math.ceil((w) / (A4_W/scale))
        rows_est = math.ceil((h) / (A4_H/scale))
        st.info(f"Estimated grid: {rows_est} rows × {cols_est} cols (~{rows_est*cols_est} pages). Cap: {HARD_PAGE_CAP}.")
    except Exception:
        pass

convert_disabled = uploaded is None
convert = st.button("Convert to A4 PDF", type="primary", disabled=convert_disabled)

if convert and uploaded:
    try:
        pdf_bytes = uploaded.getvalue()
        with st.status("Processing…", expanded=True) as s:
            s.write("Starting slicing job…")
            if HAVE_FITZ:
                buf, rows, cols, out_pages = slice_with_fitz(pdf_bytes, float(scale), int(page_number)-1)
            else:
                buf, rows, cols, out_pages = slice_with_pypdf(pdf_bytes, float(scale), int(page_number)-1)
            s.update(label="Packaging PDF…", state="running")

        st.success(f"Done! Grid: {rows} × {cols} · Pages: {out_pages}")
        st.download_button("Download A4 PDF", data=buf.getvalue(),
                           file_name="sliced_a4_portrait.pdf", mime="application/pdf")
    except Exception as e:
        st.error(f"Error: {e}")
