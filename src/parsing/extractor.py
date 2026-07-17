from __future__ import annotations

import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import fitz  # PyMuPDF
import numpy as np
from PIL import Image

from src.config import get_logger

logger = get_logger("pdf_extractor")


@dataclass
class PageExtractionResult:
    page_number: int
    text: str
    used_ocr: bool
    ocr_confidence: Optional[float]


@dataclass
class TextExtractionResult:
    full_text: str
    page_count: int
    used_ocr: bool
    pages: List[PageExtractionResult] = field(default_factory=list)

    @property
    def average_confidence(self) -> float:
        ocr_confidences = [p.ocr_confidence for p in self.pages if p.ocr_confidence is not None]
        if not ocr_confidences:
            return 1.0
        return round(float(np.mean(ocr_confidences)), 4)


class BaseTextExtractor(ABC):
    """Interface so the extraction backend can be swapped without touching
    any downstream phase code."""

    @abstractmethod
    def extract(self, pdf_path: Path) -> TextExtractionResult:
        raise NotImplementedError


class HybridPDFExtractor(BaseTextExtractor):
    """
    Primary extraction via PyMuPDF. Any page whose native text is below
    `min_native_chars` is treated as image-only and re-rendered through
    EasyOCR. Digital PDFs never touch the (slower) OCR path.
    """

    def __init__(self, min_native_chars: int = 30, ocr_gpu: bool = False, render_dpi: int = 200) -> None:
        self.min_native_chars = min_native_chars
        self.render_dpi = render_dpi
        self._ocr_reader = None
        self._ocr_gpu = ocr_gpu

    def _get_ocr_reader(self):
        if self._ocr_reader is None:
            import easyocr

            logger.info(f"Initializing EasyOCR reader (gpu={self._ocr_gpu})...")
            self._ocr_reader = easyocr.Reader(["en"], gpu=self._ocr_gpu, verbose=False)
        return self._ocr_reader

    def _ocr_page(self, page: "fitz.Page") -> Tuple[str, float]:
        pix = page.get_pixmap(dpi=self.render_dpi)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        image_array = np.array(image)

        reader = self._get_ocr_reader()
        results = reader.readtext(image_array, detail=1)

        if not results:
            return "", 0.0

        texts = [r[1] for r in results]
        confidences = [r[2] for r in results]
        return " ".join(texts), float(np.mean(confidences))

    def extract(self, pdf_path: Path) -> TextExtractionResult:
        document = fitz.open(pdf_path)
        pages: List[PageExtractionResult] = []
        any_ocr_used = False

        for page_index in range(document.page_count):
            page = document[page_index]
            native_text = page.get_text("text").strip()

            if len(native_text) >= self.min_native_chars:
                pages.append(
                    PageExtractionResult(
                        page_number=page_index, text=native_text, used_ocr=False, ocr_confidence=None
                    )
                )
            else:
                ocr_text, ocr_confidence = self._ocr_page(page)
                any_ocr_used = True
                pages.append(
                    PageExtractionResult(
                        page_number=page_index, text=ocr_text, used_ocr=True, ocr_confidence=ocr_confidence
                    )
                )
                logger.info(f"Page {page_index} required OCR fallback (confidence={ocr_confidence:.3f}).")

        document.close()
        full_text = "\n\n".join(p.text for p in pages)

        return TextExtractionResult(
            full_text=full_text, page_count=len(pages), used_ocr=any_ocr_used, pages=pages
        )


class TextCleaner:
    """
    Normalizes whitespace and unicode artifacts only. Never rewrites,
    summarizes, or alters the semantic content of the extracted text — the
    raw_extracted_text field must remain faithful to the source.
    """

    _MULTI_NEWLINE = re.compile(r"\n{3,}")
    _MULTI_SPACE = re.compile(r"[ \t]{2,}")
    _BULLET_CHARS = re.compile(r"[•●▪◦‣]")

    def clean(self, raw_text: str) -> str:
        text = unicodedata.normalize("NFKC", raw_text)
        text = self._BULLET_CHARS.sub("-", text)
        text = self._MULTI_SPACE.sub(" ", text)
        text = self._MULTI_NEWLINE.sub("\n\n", text)
        return text.strip()
