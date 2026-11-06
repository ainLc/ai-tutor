"""扫描件 OCR 适配层。

文本层够用就不用 OCR。识别失败时给出明确错误，不假装覆盖全书。
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass

log = logging.getLogger("ai-tutor.ocr")

MIN_TEXT_CHARS = 40
MAX_OCR_PAGES = 15
RENDER_SCALE = 1.6


@dataclass
class ExtractedDoc:
    text: str
    engine: str  # pypdf / ocr
    pages: int = 0
    warning: str = ""


def extract_pdf(raw: bytes) -> ExtractedDoc:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(raw))
    except Exception as e:
        raise ValueError(f"无法打开 PDF：{e}") from e

    pages = [(page.extract_text() or "") for page in reader.pages]
    text = "\n\n".join(pages).strip()
    if len(text) >= MIN_TEXT_CHARS:
        return ExtractedDoc(text=text, engine="pypdf", pages=len(pages))

    ocr_text, warning = _ocr_pdf(raw, page_count=len(pages))
    if len(ocr_text) < MIN_TEXT_CHARS:
        raise ValueError(
            "扫描版识别不出足够文字。请换清晰一些的扫描件，或先转成 Markdown / 文本再上传。"
        )
    return ExtractedDoc(
        text=ocr_text,
        engine="ocr",
        pages=min(len(pages), MAX_OCR_PAGES),
        warning=warning,
    )


def _ocr_pdf(raw: bytes, page_count: int) -> tuple[str, str]:
    try:
        import pymupdf
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as e:
        raise ValueError(
            "扫描版需要 OCR 依赖。请在 backend 目录执行："
            "pip install pymupdf rapidocr-onnxruntime"
        ) from e

    engine = RapidOCR()
    doc = pymupdf.open(stream=raw, filetype="pdf")
    parts: list[str] = []
    low_conf = 0
    limit = min(len(doc), MAX_OCR_PAGES)
    for i in range(limit):
        page = doc[i]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(RENDER_SCALE, RENDER_SCALE), alpha=False)
        png = pix.tobytes("png")
        try:
            result, _elapse = engine(png)
        except Exception as e:
            log.warning("OCR page %s failed: %s", i + 1, e)
            continue
        lines = []
        for item in result or []:
            # RapidOCR: [box, text, score]
            if not item or len(item) < 2:
                continue
            word = item[1] if not isinstance(item[1], (int, float)) else ""
            score = float(item[2]) if len(item) > 2 and item[2] is not None else 1.0
            if not word:
                continue
            if score < 0.5:
                low_conf += 1
            lines.append(str(word))
        if lines:
            parts.append(f"【第 {i + 1} 页】\n" + "\n".join(lines))
    doc.close()

    warning = ""
    if page_count > MAX_OCR_PAGES:
        warning = f"扫描件仅识别前 {MAX_OCR_PAGES} 页，后续请拆分后再传。"
    if low_conf >= 8:
        extra = "部分文字置信度偏低，讲解若不准可在听课页标记「不在资料里」。"
        warning = f"{warning} {extra}".strip()
    return "\n\n".join(parts).strip(), warning
