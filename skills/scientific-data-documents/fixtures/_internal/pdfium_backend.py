"""PDF rendering and embedded-image extraction for optional document workflows."""

from pathlib import Path


def render_pdf_pages(pdf_path, requests, *, scale=2.0):
    """Render requested one-based pages to PNGs, skipping out-of-range pages."""
    import pypdfium2 as pdfium

    rendered = []
    with pdfium.PdfDocument(pdf_path) as document:
        for page_number, target in requests:
            if not 1 <= page_number <= len(document):
                continue
            target = Path(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            page = document.get_page(page_number - 1)
            try:
                bitmap = page.render(scale=scale)
                try:
                    bitmap.to_pil().convert("RGB").save(target, format="PNG")
                finally:
                    bitmap.close()
            finally:
                page.close()
            rendered.append(target)
    return rendered


def extract_pdf_images(pdf_path, output_dir, *, max_pages=5):
    """Extract image objects from the first pages into new, numbered files."""
    import pypdfium2 as pdfium

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted = []
    with pdfium.PdfDocument(pdf_path) as document:
        for page_index in range(min(max_pages, len(document))):
            page = document.get_page(page_index)
            try:
                images = page.get_objects(filter=(pdfium.raw.FPDF_PAGEOBJ_IMAGE,))
                for image_index, image in enumerate(images, start=1):
                    prefix = output_dir / f"page_{page_index + 1:02d}_image_{image_index:02d}"
                    candidates = list(output_dir.glob(f"{prefix.name}.*"))
                    if candidates:
                        raise FileExistsError(f"refusing to replace an extracted image: {candidates[0]}")
                    image.extract(prefix, fb_format="png")
                    candidates = list(output_dir.glob(f"{prefix.name}.*"))
                    if len(candidates) != 1:
                        raise RuntimeError(f"PDF image extraction produced {len(candidates)} files for {prefix}")
                    extracted.append(str(candidates[0].resolve()))
            finally:
                page.close()
    return extracted
