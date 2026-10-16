"""Run from the repository root: python -m uvicorn backend.main:app --reload."""

from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from backend.config import Settings
from backend.errors import BackendError
from backend.exporters import export_docx, export_pptx, export_gift, export_csv
from backend.models import ProjectId, SkeletonRequest, RegeneratePartRequest, EvaluateRequest
from backend.references import extract_reference
from backend.service import ProjectService
from backend.validation import check_course


API_VERSION = "0.2.0"


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["EduAgent ACR"] = "EduAgent ACR"
    version: str = API_VERSION


def create_app(settings: Settings | None = None, skills=None) -> FastAPI:
    configuration = settings if settings is not None else Settings.from_env()
    application = FastAPI(
        title="EduAgent АЦР API",
        description=(
            "Бэкенд по чек-листу команды: анализ, каркас, утверждение, материалы, "
            "точечная правка и экспорт. execution_mode=demo означает тестовые данные "
            "из ML-ветки, а не результат обращения к модели."
        ),
        version=API_VERSION,
    )
    application.add_middleware(
        CORSMiddleware, allow_origins=list(configuration.cors_origins),
        allow_credentials=False, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )
    service = ProjectService(configuration, skills=skills)
    application.state.service = service
    application.state.settings = configuration

    @application.exception_handler(BackendError)
    async def backend_error_handler(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @application.get("/api/health", response_model=HealthResponse, tags=["system"], summary="Проверить доступность HTTP API")
    def health_check():
        return HealthResponse()

    @application.post("/api/projects/analyze", tags=["projects"], summary="Проанализировать запрос и файлы")
    async def analyze(
        query: Annotated[str, Form(min_length=1, max_length=30000)],
        files: Annotated[list[UploadFile] | None, File()] = None,
        project_id: Annotated[ProjectId | None, Form()] = None,
    ):
        uploads = files or []
        try:
            if len(uploads) > configuration.max_files:
                raise BackendError(413, "too_many_references", f"Разрешено до {configuration.max_files} файлов")
            references = []
            characters = 0
            for upload in uploads:
                data = await upload.read(configuration.max_file_bytes + 1)
                item = await run_in_threadpool(extract_reference, upload.filename or "reference", data, configuration.max_file_bytes, configuration.max_reference_chars)
                references.append(item)
                characters += len(item.text)
            if characters > configuration.max_reference_chars:
                raise BackendError(413, "references_text_too_large", "Общий объём текста референсов превышает лимит")
            return await service.analyze(query, references, project_id)
        finally:
            for upload in uploads:
                await upload.close()

    @application.post("/api/projects/skeleton", tags=["projects"], summary="Создать каркас программы")
    async def skeleton(request: SkeletonRequest):
        return await service.skeleton(request)

    @application.get("/api/projects/{project_id}", tags=["projects"], summary="Прочитать сохранённый проект")
    def get_project(project_id: ProjectId):
        return service.store.load(project_id).public()

    @application.put("/api/projects/{project_id}/skeleton", tags=["projects"], summary="Сохранить правки и утвердить каркас")
    async def approve(project_id: ProjectId, updated_course: dict):
        return await service.approve(project_id, updated_course)

    @application.post("/api/projects/{project_id}/generate-content", tags=["projects"], summary="Создать материалы утверждённой программы")
    async def generate(project_id: ProjectId):
        return await service.generate(project_id)

    @application.post("/api/projects/{project_id}/regenerate-part", tags=["projects"], summary="Пересобрать тему или вопрос")
    async def regenerate(project_id: ProjectId, request: RegeneratePartRequest):
        return await service.regenerate(project_id, request)

    @application.get("/api/projects/{project_id}/export/{file_format}", tags=["exports"], summary="Скачать DOCX, PPTX, GIFT, CSV или JSON")
    async def export(project_id: ProjectId, file_format: Literal["docx", "pptx", "gift", "csv", "json"], revision: int | None = None):
        record = service.store.load(project_id)
        if revision is not None and revision != record.revision:
            raise BackendError(409, "revision_conflict", "Версия проекта изменилась", current_revision=record.revision)
        if file_format == "json":
            return JSONResponse(record.public(), headers={"Content-Disposition": f'attachment; filename="Course_{project_id}.json"', "Cache-Control": "no-store"})
        if record.course is None or record.course.status != "completed" or record.busy:
            raise BackendError(409, "materials_required", "Сначала создайте полный комплект материалов")
        check_course(record.course, completed=True)
        exporters = {
            "docx": (export_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            "pptx": (export_pptx, "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
            "gift": (export_gift, "text/plain; charset=utf-8"),
            "csv": (export_csv, "text/csv; charset=utf-8"),
        }
        builder, media_type = exporters[file_format]
        content = await run_in_threadpool(builder, record)
        return Response(content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="Course_{project_id}.{file_format}"', "Cache-Control": "no-store"})

    @application.post("/api/v1/evaluate", tags=["evaluation"], summary="Единая точка входа с сохранением этапа утверждения")
    async def evaluate(request: EvaluateRequest):
        if request.action in {"analyze", "skeleton"} and not request.query.strip():
            raise BackendError(422, "empty_query", "Опишите задачу методиста")
        if request.action == "analyze":
            return await service.analyze(request.query, [], request.project_id)
        if request.action == "skeleton":
            if request.approved:
                raise BackendError(422, "approval_requires_review", "Сначала получите каркас, затем передайте отдельное действие approve")
            try:
                return await service.skeleton(SkeletonRequest(**request.model_dump(include=set(SkeletonRequest.model_fields))))
            except BackendError as exc:
                if exc.detail["code"] != "clarifications_required":
                    raise
                return {"status": "clarifying", "project_id": exc.detail["project_id"], **exc.detail["analysis"]}
        if request.project_id is None:
            raise BackendError(422, "project_id_required", "Для продолжения нужен project_id")
        if request.action == "approve":
            if not request.approved:
                raise BackendError(409, "approval_required", "Утверждение требует approved=true")
            return await service.approve(request.project_id, request.course or {})
        if request.action == "generate":
            return await service.generate(request.project_id)
        if not request.element_type or not request.element_id or not request.instruction.strip():
            raise BackendError(422, "regeneration_fields_required", "Нужны element_type, element_id и instruction")
        return await service.regenerate(request.project_id, RegeneratePartRequest(element_type=request.element_type, element_id=request.element_id, instruction=request.instruction))

    return application


app = create_app()
