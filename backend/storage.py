"""One atomic JSON snapshot per project. Run one Uvicorn worker."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock

from backend.errors import BackendError
from backend.models import ProjectRecord


class ProjectStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def _path(self, project_id: str) -> Path:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", project_id):
            raise BackendError(422, "invalid_project_id", "Некорректный идентификатор проекта")
        return self.directory / f"{project_id}.json"

    def load(self, project_id: str) -> ProjectRecord:
        path = self._path(project_id)
        try:
            return ProjectRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise BackendError(404, "project_not_found", "Проект не найден") from exc
        except (ValueError, OSError) as exc:
            raise BackendError(500, "project_read_failed", "Не удалось прочитать сохранённый проект") from exc

    def save(self, record: ProjectRecord) -> ProjectRecord:
        path = self._path(record.project_id)
        with self._lock:
            current_revision = self.load(record.project_id).revision if path.exists() else 0
            if current_revision != record.revision:
                raise BackendError(409, "revision_conflict", "Проект уже изменён. Загрузите свежую версию.", current_revision=current_revision)
            saved = record.model_copy(deep=True)
            saved.revision += 1
            saved.updated_at = datetime.now(timezone.utc)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory, suffix=".tmp", delete=False) as output:
                    temporary = Path(output.name)
                    json.dump(saved.model_dump(mode="json"), output, ensure_ascii=False, indent=2)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, path)
            except OSError as exc:
                raise BackendError(500, "project_write_failed", "Не удалось сохранить проект") from exc
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
            return saved
