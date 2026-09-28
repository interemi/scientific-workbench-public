"""Exercise PDF rendering and image recovery without changing the source PDF."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _internal.pdfium_backend import extract_pdf_images, render_pdf_pages  # noqa: E402


@unittest.skipUnless(
    importlib.util.find_spec("pypdfium2") and importlib.util.find_spec("PIL"),
    "Full document PDF dependencies are not installed",
)
class PdfiumBackendTest(unittest.TestCase):
    def test_renders_and_extracts_embedded_image_without_replacing_source(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "synthetic.pdf"
            Image.new("RGB", (20, 15), (23, 141, 196)).save(source, format="PDF", resolution=72)
            before = hashlib.sha256(source.read_bytes()).hexdigest()

            rendered = render_pdf_pages(
                source,
                [(1, root / "rendered.png"), (2, root / "out-of-range.png")],
            )
            self.assertEqual(rendered, [root / "rendered.png"])
            with Image.open(rendered[0]) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (40, 30))

            extracted = extract_pdf_images(source, root / "figures")
            self.assertEqual(len(extracted), 1)
            with Image.open(extracted[0]) as image:
                self.assertEqual(image.size, (20, 15))
            with self.assertRaises(FileExistsError):
                extract_pdf_images(source, root / "figures")

            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
