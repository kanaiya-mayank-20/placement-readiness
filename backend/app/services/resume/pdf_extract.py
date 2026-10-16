"""PDF text extraction with multi-extractor fallback (pdfplumber -> pypdf)."""

import logging

log = logging.getLogger("resume.pdf")

MAX_PAGES = 15


def is_pdf(content: bytes) -> bool:
    return content[:5] == b"%PDF-" or content[:1024].find(b"%PDF-") != -1


def extract_text(path: str) -> str:
    texts = []

    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:MAX_PAGES]:
                texts.append(page.extract_text() or "")
        texts.append("")  # keep order
        plumber_text = "\n".join(t for t in texts if t)
        if plumber_text:
            return plumber_text
    except Exception as exc:
        log.warning("pdfplumber failed: %s", exc)

    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        pypdf_text = "\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PAGES])
        if pypdf_text:
            return pypdf_text
    except Exception as exc:
        log.warning("pypdf failed: %s", exc)

    return ""
