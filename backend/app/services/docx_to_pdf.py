"""Genuine DOCX → PDF conversion for authorized downloads.

Conversion strategy (no paid services):
1. **Preferred:** LibreOffice / soffice headless when installed on the host.
   Preserves layout, fonts, tables, images, and pagination far more faithfully.
2. **Fallback:** ReportLab text/table extraction from ``word/document.xml``.
   Does **not** preserve full Word layout; images are omitted in the fallback.

Never renames a ``.docx`` file to ``.pdf``. Output is validated as ``%PDF``.
Temporary conversion files live only under a private temp directory and are
always deleted in a ``finally`` block.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)

WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


class DocxConversionError(Exception):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class PdfConversionResult:
    pdf_bytes: bytes
    method: str  # "libreoffice" | "reportlab_fallback"


def _find_libreoffice() -> str | None:
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    # Common Windows install path when not on PATH.
    candidates = [
        Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
        Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _convert_via_libreoffice(docx_bytes: bytes) -> bytes:
    soffice = _find_libreoffice()
    if soffice is None:
        raise DocxConversionError(
            "LibreOffice is not available",
            reason_code="LIBREOFFICE_UNAVAILABLE",
        )

    with TemporaryDirectory(prefix="trustvault_docx2pdf_") as tmp:
        tmp_path = Path(tmp)
        # Restrictive permissions where the OS supports them.
        try:
            tmp_path.chmod(0o700)
        except OSError:
            pass

        src = tmp_path / "source.docx"
        src.write_bytes(docx_bytes)
        try:
            completed = subprocess.run(
                [
                    soffice,
                    "--headless",
                    "--nologo",
                    "--nofirststartwizard",
                    "--norestore",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(tmp_path),
                    str(src),
                ],
                check=False,
                capture_output=True,
                timeout=90,
            )
        except subprocess.TimeoutExpired as exc:
            raise DocxConversionError(
                "DOCX to PDF conversion timed out",
                reason_code="CONVERSION_TIMEOUT",
            ) from exc
        except OSError as exc:
            raise DocxConversionError(
                "DOCX to PDF converter could not be started",
                reason_code="CONVERTER_START_FAILED",
            ) from exc

        pdf_path = tmp_path / "source.pdf"
        if completed.returncode != 0 or not pdf_path.is_file():
            logger.warning(
                "LibreOffice conversion failed",
                extra={
                    "returncode": completed.returncode,
                    "stderr_len": len(completed.stderr or b""),
                },
            )
            raise DocxConversionError(
                "DOCX to PDF conversion failed",
                reason_code="LIBREOFFICE_FAILED",
            )

        pdf_bytes = pdf_path.read_bytes()
        if not pdf_bytes.startswith(b"%PDF"):
            raise DocxConversionError(
                "PDF conversion produced invalid output",
                reason_code="INVALID_PDF_OUTPUT",
            )
        return pdf_bytes
    # TemporaryDirectory removes files here — no public or leftover paths.


def _paragraph_text(para: ET.Element) -> str:
    texts = [node.text or "" for node in para.findall(".//w:t", WORD_NS)]
    return "".join(texts).strip()


def _extract_blocks(docx_bytes: bytes) -> list[tuple[str, object]]:
    """Return story blocks: ('p', text) or ('table', list[list[str]])."""
    try:
        with zipfile.ZipFile(BytesIO(docx_bytes)) as archive:
            xml_bytes = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise DocxConversionError(
            "DOCX could not be read for PDF conversion",
            reason_code="DOCX_UNREADABLE",
        ) from exc

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise DocxConversionError(
            "DOCX XML is invalid",
            reason_code="DOCX_XML_INVALID",
        ) from exc

    body = root.find("w:body", WORD_NS)
    if body is None:
        return [("p", "(Empty document)")]

    blocks: list[tuple[str, object]] = []
    for child in list(body):
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = _paragraph_text(child)
            if text:
                blocks.append(("p", text))
        elif tag == "tbl":
            rows: list[list[str]] = []
            for tr in child.findall("./w:tr", WORD_NS):
                cells = [
                    _paragraph_text(tc) or " "
                    for tc in tr.findall("./w:tc", WORD_NS)
                ]
                if cells:
                    rows.append(cells)
            if rows:
                blocks.append(("table", rows))

    if not blocks:
        blocks = [("p", "(Empty document)")]
    return blocks


def _escape_rl(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _convert_via_reportlab(docx_bytes: bytes) -> bytes:
    """Fallback converter — text and simple tables only; not full layout fidelity."""
    blocks = _extract_blocks(docx_bytes)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story: list = []

    for kind, payload in blocks:
        if kind == "p":
            story.append(Paragraph(_escape_rl(str(payload)), styles["Normal"]))
            story.append(Spacer(1, 8))
        elif kind == "table":
            rows = payload
            assert isinstance(rows, list)
            table_data = [
                [Paragraph(_escape_rl(cell), styles["Normal"]) for cell in row]
                for row in rows
            ]
            table = Table(table_data, hAlign="LEFT")
            table.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 12))

    try:
        doc.build(story)
    except Exception as exc:  # noqa: BLE001
        raise DocxConversionError(
            "PDF rendering failed",
            reason_code="PDF_RENDER_FAILED",
        ) from exc

    pdf_bytes = buffer.getvalue()
    if not pdf_bytes.startswith(b"%PDF"):
        raise DocxConversionError(
            "PDF conversion produced invalid output",
            reason_code="INVALID_PDF_OUTPUT",
        )
    return pdf_bytes


def convert_docx_bytes_to_pdf(docx_bytes: bytes) -> bytes:
    """Convert DOCX bytes into a validated PDF byte stream."""
    return convert_docx_bytes_to_pdf_detailed(docx_bytes).pdf_bytes


def convert_docx_bytes_to_pdf_detailed(docx_bytes: bytes) -> PdfConversionResult:
    if not docx_bytes:
        raise DocxConversionError(
            "Empty DOCX cannot be converted",
            reason_code="EMPTY_DOCX",
        )

    if _find_libreoffice() is not None:
        try:
            pdf_bytes = _convert_via_libreoffice(docx_bytes)
            return PdfConversionResult(pdf_bytes=pdf_bytes, method="libreoffice")
        except DocxConversionError as exc:
            # Fall back when LibreOffice is present but fails for this file.
            logger.warning(
                "LibreOffice conversion unavailable for this file; using fallback",
                extra={"reason_code": exc.reason_code},
            )

    pdf_bytes = _convert_via_reportlab(docx_bytes)
    return PdfConversionResult(pdf_bytes=pdf_bytes, method="reportlab_fallback")
