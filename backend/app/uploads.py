"""Limits and XLSX safety checks for file uploads (the weekly workbook upload).

Moved here from the removed legacy CSV/XLSX import module (2026-11-20) without changing values
or behaviour: 10MB per file, 5,000 rows, 64 columns, and the ZIP compression-ratio check that
rejects decompression bombs before openpyxl reads the file.
"""

from datetime import date, datetime
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from app.errors import CompatibilityError

MAX_FILE_BYTES = 10 * 1024 * 1024
# Multipart overhead (boundary, form fields) on top of the file itself.
MAX_REQUEST_BYTES = MAX_FILE_BYTES + 64 * 1024
MAX_ROWS = 5_000
MAX_COLUMNS = 64
# Phase 11-2-B-2 (SEC-06). A real weekly workbook: ~20 ZIP entries, <100KB unpacked, ~400 rows.
MAX_ZIP_ENTRIES = 1_000
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024  # sum of the declared sizes of every entry
# Rows the parser may walk through, blank ones included. openpyxl fills the gap between two
# row numbers with blank rows, so a few-KB file naming row 1,048,576 cost ~27s of CPU per sheet.
MAX_SCANNED_ROWS = 50_000
UPLOAD_PATHS = frozenset(
    {"/api/lesson-uploads/sheets", "/api/lesson-uploads/preview", "/api/lesson-uploads/confirm"}
)


def check_xlsx_zip(content: bytes) -> None:
    if len(content) < 4 or content[:2] != b"PK":
        raise CompatibilityError(400, "INVALID_XLSX", "유효한 XLSX 파일이 아닙니다.")
    """Checks the ZIP directory only — nothing is unpacked here. Declared sizes can be trusted
    as an upper bound: Python's zipfile (used by openpyxl) never returns more bytes for an entry
    than its declared size."""
    try:
        with ZipFile(BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise CompatibilityError(400, "INVALID_XLSX", "파일 형식 또는 내용을 확인해주세요.")
            if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
                raise CompatibilityError(400, "INVALID_XLSX", "파일 형식 또는 내용을 확인해주세요.")
            for info in infos:
                if info.file_size and info.compress_size / info.file_size < 0.01:
                    raise CompatibilityError(
                        400, "INVALID_XLSX", "파일 형식 또는 내용을 확인해주세요."
                    )
    except BadZipFile as exc:
        raise CompatibilityError(
            400, "INVALID_XLSX", "파일 형식 또는 내용을 확인해주세요."
        ) from exc


def format_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
