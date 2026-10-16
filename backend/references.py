"""Extract references in memory, including nested DOCX tables."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

from backend.errors import BackendError
from backend.models import ReferenceFile


def _blocks(container):
    for block in container.iter_inner_content():
        if isinstance(block, Paragraph):
            if block.text.strip():
                yield block.text
        elif isinstance(block, Table):
            yield "[ТАБЛИЦА]"
            for row in block.rows:
                # Merged cells can share the same underlying XML element.
                seen = set()
                cells = []
                for cell in row.cells:
                    if cell._tc not in seen:
                        cells.append(" / ".join(_blocks(cell)))
                        seen.add(cell._tc)
                yield " | ".join(cells)
            yield "[/ТАБЛИЦА]"


def extract_reference(filename: str, data: bytes, max_bytes: int, max_chars: int) -> ReferenceFile:
    filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    kind = Path(filename).suffix.lower().lstrip(".")
    if kind not in {"docx", "pdf"}:
        raise BackendError(415, "unsupported_reference", "Поддерживаются только DOCX и PDF", filename=filename)
    if not data:
        raise BackendError(422, "empty_reference", "Загружен пустой файл", filename=filename)
    if len(data) > max_bytes:
        raise BackendError(413, "reference_too_large", "Файл превышает разрешённый размер", filename=filename)
    warnings = []
    try:
        if kind == "docx":
            with ZipFile(BytesIO(data)) as package:
                if sum(item.file_size for item in package.infolist()) > 50 * 1024 * 1024:
                    raise BackendError(413, "docx_unpacked_too_large", "Содержимое DOCX превышает 50 МБ")
            text = "\n".join(_blocks(Document(BytesIO(data))))
        else:
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted and not reader.decrypt(""):
                raise BackendError(422, "encrypted_pdf", "PDF защищён паролем", filename=filename)
            pages = []
            for number, page in enumerate(reader.pages, 1):
                value = page.extract_text() or ""
                if not value.strip():
                    warnings.append(f"Страница {number} файла {filename}: текст не найден; возможно, требуется OCR.")
                pages.append(f"[Страница {number}]\n{value}" if value.strip() else "")
            text = "\n".join(pages)
    except BackendError:
        raise
    except Exception as exc:
        raise BackendError(422, "reference_parse_failed", "Файл повреждён или не поддерживается парсером", filename=filename) from exc
    if not text.strip():
        raise BackendError(422, "reference_has_no_text", "В файле нет извлекаемого текста. Для скана требуется OCR.", filename=filename)
    if len(text) > max_chars:
        raise BackendError(413, "reference_text_too_large", "Слишком большой объём текста в референсе", filename=filename)
    return ReferenceFile(filename=filename, kind=kind, sha256=sha256(data).hexdigest(), text=text, warnings=warnings)
