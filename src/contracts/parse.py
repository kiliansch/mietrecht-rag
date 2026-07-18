"""Extract plain text from uploaded contract files.

Supports PDF (text + OCR fallback for scanned pages), DOCX, TXT,
and direct image input (PNG/JPG) using pytesseract with German language pack.

System prerequisites (not managed by uv):
    tesseract-ocr, tesseract-ocr-deu, poppler-utils
"""

from __future__ import annotations

import os


_OCR_MIN_CHARS = 100  # if PDF yields fewer chars, assume scanned and fall back to OCR


def _require_binary(name: str) -> None:
    """Raise ImportError with a helpful message if a required binary is missing."""
    import shutil
    if shutil.which(name) is None:
        raise ImportError(
            f"Required system binary '{name}' not found. "
            f"Install it with: sudo apt install tesseract-ocr tesseract-ocr-deu poppler-utils"
        )


def _extract_pdf(data: bytes) -> str:
    import pypdf

    reader = pypdf.PdfReader(__import__("io").BytesIO(data))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if len(text.strip()) >= _OCR_MIN_CHARS:
        return text

    # Scanned PDF — fall back to OCR via pdf2image + pytesseract
    _require_binary("pdftoppm")
    _require_binary("tesseract")
    import pytesseract  # type: ignore[import-untyped]
    from pdf2image import convert_from_bytes

    images = convert_from_bytes(data)
    pages = [pytesseract.image_to_string(img, lang="deu") for img in images]
    return "\n".join(pages)


def _extract_docx(data: bytes) -> str:
    import io
    import docx

    doc = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def _extract_image(data: bytes) -> str:
    import io
    import PIL.Image
    import pytesseract  # type: ignore[import-untyped]

    _require_binary("tesseract")
    img = PIL.Image.open(io.BytesIO(data))
    return pytesseract.image_to_string(img, lang="deu")


def extract_text(data: bytes, filename: str) -> str:
    """Extract plain text from *data* based on *filename* extension.

    Raises:
        ValueError: if the file extension is unsupported.
        ImportError: if a required system binary (tesseract, pdftoppm) is missing.
    """
    ext = os.path.splitext(filename.lower())[1]
    if ext == ".pdf":
        return _extract_pdf(data)
    if ext == ".docx":
        return _extract_docx(data)
    if ext == ".txt":
        return data.decode("utf-8", errors="replace")
    if ext in (".png", ".jpg", ".jpeg"):
        return _extract_image(data)
    raise ValueError(f"Unsupported file type: '{ext}'. Supported: pdf, docx, txt, png, jpg.")
