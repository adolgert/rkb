"""Translate PDFs to Markdown using marker-pdf and store beside the PDF."""

from __future__ import annotations

import gc
import importlib.metadata
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from rkb.collection.config import CollectionConfig

logger = logging.getLogger(__name__)

_PROGRESS_THRESHOLD = 5
_OUTPUT_FILENAME = "extracted.md"
DEFAULT_CHUNK_PAGES = 50


def marker_pdf_version() -> str:
    return importlib.metadata.version("marker-pdf")


def tool_subdir(version: str | None = None) -> str:
    return f"marker-pdf-{version or marker_pdf_version()}"


@dataclass
class TranslateFailure:
    content_sha256: str
    error: str


@dataclass
class TranslateSummary:
    total: int = 0
    translated: int = 0
    skipped: int = 0
    failed: int = 0
    failures: list[TranslateFailure] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "translated": self.translated,
            "skipped": self.skipped,
            "failed": self.failed,
            "failures": [
                {"content_sha256": f.content_sha256, "error": f.error}
                for f in self.failures
            ],
        }

    def exit_code(self) -> int:
        return 2 if self.failed > 0 else 0


def _find_pdfs_to_translate(library_root: Path, *, all_pdfs: bool, subdir: str) -> list[Path]:
    """Return PDF paths sorted smallest-first that need translation.

    Default: PDFs with no extractions directory at all.
    --all: PDFs missing the specific marker-pdf-{version} subdir.
    """
    pdfs = []
    for pdf in library_root.glob("sha256/*/*/*/*"):
        if pdf.suffix.lower() != ".pdf":
            continue
        hash_dir = pdf.parent
        extractions = hash_dir / "extractions"
        if all_pdfs:
            if not (extractions / subdir / _OUTPUT_FILENAME).exists():
                pdfs.append(pdf)
        elif not extractions.exists():
            pdfs.append(pdf)
    pdfs.sort(key=lambda p: p.stat().st_size)
    return pdfs


def _page_count(pdf_path: Path) -> int | None:
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(pdf_path)).pages)
    except Exception:
        return None


def _chunk_ranges(page_count: int, chunk_size: int) -> list[str]:
    """Return list of 'start-end' page range strings (0-indexed, inclusive)."""
    return [
        f"{start}-{min(start + chunk_size - 1, page_count - 1)}"
        for start in range(0, page_count, chunk_size)
    ]


_PAGE_IMG_RE = re.compile(r"_page_(\d+)_")


def _offset_images(text: str, images: dict, start_page: int) -> tuple[str, dict]:
    """Rename image keys and fix references so page numbers are absolute."""
    if start_page == 0:
        return text, images
    renamed: dict = {}
    for name, img in images.items():
        new_name = _PAGE_IMG_RE.sub(
            lambda m: f"_page_{int(m.group(1)) + start_page}_", name
        )
        renamed[new_name] = img
        if new_name != name:
            text = text.replace(name, new_name)
    return text, renamed


def _build_config_dict(gemini_api_key: str, gemini_model: str, page_range: str | None) -> dict:
    from marker.config.parser import ConfigParser
    opts: dict = {
        "use_llm": True,
        "llm_service": "marker.services.gemini.GoogleGeminiService",
        "GoogleGeminiService_gemini_model_name": gemini_model,
        "GoogleGeminiService_gemini_api_key": gemini_api_key,
        "output_format": "markdown",
        "disable_tqdm": True,
    }
    if page_range is not None:
        opts["page_range"] = page_range
    return ConfigParser(opts).generate_config_dict()


def _translate_one(
    pdf_path: Path,
    models: dict,
    *,
    gemini_api_key: str,
    gemini_model: str,
    chunk_pages: int,
) -> tuple[str, dict]:
    """Convert one PDF to (markdown_text, images_dict), chunking if needed."""
    from marker.converters.pdf import PdfConverter
    from marker.output import text_from_rendered

    pages = _page_count(pdf_path)

    if pages is None or pages <= chunk_pages:
        config_dict = _build_config_dict(gemini_api_key, gemini_model, None)
        rendered = PdfConverter(artifact_dict=models, config=config_dict)(str(pdf_path))
        text, _, images = text_from_rendered(rendered)
        return text, images

    ranges = _chunk_ranges(pages, chunk_pages)
    logger.info(
        "Chunking %s (%d pages) into %d chunks of %d",
        pdf_path.name[:50], pages, len(ranges), chunk_pages,
    )
    all_texts: list[str] = []
    all_images: dict = {}

    for page_range in ranges:
        start_page = int(page_range.split("-")[0])
        config_dict = _build_config_dict(gemini_api_key, gemini_model, page_range)
        rendered = PdfConverter(artifact_dict=models, config=config_dict)(str(pdf_path))
        text, _, images = text_from_rendered(rendered)
        text, images = _offset_images(text, images, start_page)
        all_texts.append(text)
        all_images.update(images)
        del rendered
        gc.collect()

    return "\n\n".join(all_texts), all_images


def _iter_with_progress(items: list, description: str):
    if len(items) <= _PROGRESS_THRESHOLD:
        return items
    try:
        from tqdm import tqdm
    except ImportError:
        return items
    return tqdm(items, desc=description, unit="pdf")


def _save_output(dest_dir: Path, text: str, images: dict) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / _OUTPUT_FILENAME).write_text(text, encoding="utf-8")
    for name, img in images.items():
        img.save(dest_dir / name)


def translate_collection(
    config: CollectionConfig,
    *,
    gemini_api_key: str,
    gemini_model: str = "gemini-2.5-flash",
    dry_run: bool = False,
    all_pdfs: bool = False,
    chunk_pages: int = DEFAULT_CHUNK_PAGES,
) -> TranslateSummary:
    """Translate PDFs to Markdown and store beside the PDF in the canonical store.

    PDFs are processed smallest-first. PDFs exceeding chunk_pages pages are split
    into page-range chunks and recombined, keeping memory usage bounded.

    Args:
        config: Collection configuration (provides library_root).
        gemini_api_key: Gemini API key for LLM-assisted extraction.
        gemini_model: Gemini model name (default: gemini-2.5-flash).
        dry_run: Report what would happen without writing files.
        all_pdfs: Translate every PDF, not just those with no extraction at all.
        chunk_pages: Maximum pages per conversion chunk (default: 50).
    """
    version = marker_pdf_version()
    subdir = tool_subdir(version)
    summary = TranslateSummary()

    pdfs = _find_pdfs_to_translate(config.library_root, all_pdfs=all_pdfs, subdir=subdir)
    summary.total = len(pdfs)

    if dry_run or summary.total == 0:
        summary.skipped = summary.total
        return summary

    from marker.models import create_model_dict

    logger.info("Loading marker-pdf models (version %s)…", version)
    models = create_model_dict()
    logger.info("Models loaded. Translating %d PDFs (chunk_pages=%d).", summary.total, chunk_pages)

    for pdf_path in _iter_with_progress(pdfs, f"Translating ({subdir})"):
        sha256 = pdf_path.parent.name
        dest_dir = pdf_path.parent / "extractions" / subdir
        try:
            text, images = _translate_one(
                pdf_path,
                models,
                gemini_api_key=gemini_api_key,
                gemini_model=gemini_model,
                chunk_pages=chunk_pages,
            )
            _save_output(dest_dir, text, images)
            summary.translated += 1
            logger.debug("Translated %s -> %s", sha256[:12], dest_dir)
        except Exception as exc:
            summary.failed += 1
            summary.failures.append(TranslateFailure(content_sha256=sha256, error=str(exc)))
            logger.warning("Failed %s: %s", sha256[:12], exc)

    return summary
