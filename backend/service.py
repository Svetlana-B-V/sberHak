import asyncio
from collections import Counter
from copy import deepcopy
import time
from uuid import uuid4

from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from ml.schemas import CourseProgram, LiteratureItem
from backend.config import Settings
from backend.errors import BackendError
from backend.models import ProjectRecord, SkeletonRequest, RegeneratePartRequest
from backend.skills import Skills
from backend.storage import ProjectStore
from backend.validation import check_course, check_clarifications, mark_unverified_sources


class ProjectService:
    def __init__(self, settings: Settings, skills=None):
        self.settings = settings
        self.store = ProjectStore(settings.data_dir)
        self.skills = skills if skills is not None else Skills(settings)
        self.locks: dict[str, asyncio.Lock] = {}

    def lock(self, project_id):
        return self.locks.setdefault(project_id, asyncio.Lock())

    def new_record(self, query, references=()):
        warnings = [warning for item in references for warning in item.warnings]
        if self.settings.ml_mode == "demo":
            warnings.append("Демонстрационные данные ML-ветки: это проверка интеграции, не готовая учебная программа.")
        warnings.append("Существование и актуальность источников требуют отдельной проверки; домен сайта этого не подтверждает.")
        return ProjectRecord(project_id=uuid4().hex, query=query, references=list(references), execution_mode=self.settings.ml_mode, warnings=warnings)

    async def call(self, record, operation, *args, timeout=None):
        budget = timeout if timeout is not None else self.settings.ml_timeout_seconds
        if budget <= 0:
            raise BackendError(504, "ml_timeout", "Истекло время генерации комплекта")
        try:
            result, metrics = await asyncio.wait_for(
                run_in_threadpool(self.skills.run, operation, *args, references=record.reference_text(), timeout_seconds=budget),
                timeout=budget,
            )
        except asyncio.TimeoutError as exc:
            raise BackendError(504, "ml_timeout", "Истекло время выполнения ML-операции") from exc
        except ValidationError as exc:
            raise BackendError(502, "ml_contract_failed", "ML-функция вернула данные, не соответствующие ml/schemas.py") from exc
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(502, "ml_skill_failed", "Не удалось выполнить функцию ML-навыка") from exc
        for field in ("prompt_tokens", "completion_tokens", "total_tokens", "api_calls", "elapsed_seconds"):
            previous = record.metrics.get(field, 0)
            value = metrics.get(field, 0)
            record.metrics[field] = previous + value if previous is not None and value is not None else None
        record.metrics.update(mode=metrics.get("mode"), model=metrics.get("model"), estimated_cost_rub=None, saved_methodist_hours=None)
        return result

    async def analyze(self, query, references, project_id=None):
        if not query.strip():
            raise BackendError(422, "empty_query", "Опишите задачу методиста")
        record = self.store.load(project_id) if project_id else self.new_record(query, references)
        async with self.lock(record.project_id):
            if project_id:
                record = self.store.load(project_id)
                record.query = query
                record.references = references if references else record.references
                record.course = None
                record.slide_modules = {}
                record.module_literature = {}
            analysis = await self.call(record, "analyze", query, record.reference_text())
            record.analysis = check_clarifications(analysis, query)
            record = self.store.save(record)
            return {**record.analysis.model_dump(), "project_id": record.project_id, "revision": record.revision, "execution_mode": record.execution_mode, "backend_warnings": record.warnings}

    async def skeleton(self, request: SkeletonRequest):
        record = self.store.load(request.project_id) if request.project_id else self.new_record(request.query)
        async with self.lock(record.project_id):
            if request.project_id:
                record = self.store.load(request.project_id)
            query = request.query
            context = request.clarifications
            if request.template_type:
                context += "\nТип программы: " + ("повышение квалификации" if request.template_type == "dpp_pk" else "общеразвивающая")
            if request.total_hours is not None:
                context += f"\nОбъём: {request.total_hours} часов."
            combined = query + "\n" + context
            analysis = await self.call(record, "analyze", combined, record.reference_text())
            analysis = check_clarifications(analysis, combined)
            record.analysis = analysis
            record.query = query
            if not analysis.is_complete:
                record.course = None
                record.slide_modules = {}
                record.module_literature = {}
                record = self.store.save(record)
                raise BackendError(409, "clarifications_required", "Сначала ответьте на уточняющие вопросы", project_id=record.project_id, analysis=analysis.model_dump())
            hours = request.total_hours if request.total_hours is not None else analysis.extracted_params.get("total_hours")
            if isinstance(hours, bool) or not isinstance(hours, int) or hours < 1:
                raise BackendError(422, "invalid_total_hours", "Укажите положительное целое число академических часов")
            template = request.template_type or analysis.template_type
            record.analysis.template_type = template
            record.analysis.extracted_params["total_hours"] = hours
            course = await self.call(record, "skeleton", record.project_id, combined, template, hours, context)
            course.project_id = record.project_id
            course.status = "skeleton_ready"
            mark_unverified_sources(course)
            check_course(course)
            record.course = course
            record.slide_modules = {}
            record.module_literature = {}
            record.execution_mode = self.settings.ml_mode
            await self.validate(record)
            return self.store.save(record).public()

    async def validate(self, record):
        check_course(record.course, completed=record.course.status == "completed")
        mark_unverified_sources(record.course)
        report = await self.call(record, "validate", record.course)
        report.metrics = deepcopy(record.metrics)
        if not report.is_valid:
            raise BackendError(422, "ml_validation_failed", "Программа не прошла проверку ML-навыка", errors=report.errors)

    def require_course(self, record, status=None):
        if record.course is None:
            raise BackendError(409, "skeleton_required", "Сначала создайте каркас программы")
        if status and record.course.status != status:
            raise BackendError(409, "invalid_project_status", f"Операция требует статуса {status}", current_status=record.course.status)
        if record.execution_mode != self.settings.ml_mode:
            raise BackendError(409, "execution_mode_changed", "Создайте новый каркас после переключения режима ML")

    async def approve(self, project_id, updates):
        async with self.lock(project_id):
            record = self.store.load(project_id)
            self.require_course(record)
            if updates.get("project_id", project_id) != project_id:
                raise BackendError(422, "project_id_mismatch", "project_id в теле и адресе должны совпадать")
            if "revision" in updates and updates["revision"] != record.revision:
                raise BackendError(409, "revision_conflict", "Загрузите свежую версию каркаса", current_revision=record.revision)
            protected = {"project_id", "status", "tests", "seminars", "lecture_slides", "literature", "validation_report"}
            payload = record.course.model_dump()
            payload.update({key: value for key, value in updates.items() if key in CourseProgram.model_fields and key not in protected})
            try:
                candidate = CourseProgram(**payload)
            except ValidationError as exc:
                raise BackendError(422, "invalid_course_data", "Правки не соответствуют схеме CourseProgram") from exc
            for mod in candidate.modules:
                for topic in mod.topics:
                    if any(getattr(topic, field) < 0 for field in ("total_hours", "lecture_hours", "practice_hours", "lab_hours", "srs_hours")):
                        raise BackendError(422, "negative_hours", "Часы не могут быть отрицательными")
            if candidate.total_hours <= candidate.ia_hours or candidate.ia_hours < 0:
                raise BackendError(422, "invalid_ia_hours", "Часы ИА должны быть неотрицательными и меньше общего объёма")
            duration = candidate.duration_days
            balanced = await self.call(record, "balance", candidate.model_dump(), candidate.total_hours)
            if balanced.get("ia_hours") != candidate.ia_hours:
                raise BackendError(422, "attestation_hours_changed", "Балансировщик ML изменил часы итоговой аттестации. Нужна корректировка балансировщика или явная правка каркаса.")
            balanced.update(status="approved", tests=[], seminars=[], lecture_slides=[], literature=[], validation_report=None, duration_days=duration)
            record.course = CourseProgram(**balanced)
            record.slide_modules = {}
            record.module_literature = {}
            await self.validate(record)
            return self.store.save(record).public()

    def _subset(self, course, module):
        subset = course.model_copy(deep=True)
        subset.modules = [module.model_copy(deep=True)]
        known = {key for topic in module.topics for key in topic.linked_competencies}
        subset.competencies = [comp for comp in subset.competencies if comp.id in known]
        subset.tests, subset.seminars, subset.lecture_slides, subset.literature = [], [], [], []
        return subset

    def _named_items(self, items, prefix):
        counts = Counter()
        result = []
        for item in items:
            item = item.model_copy(deep=True)
            counts[item.linked_topic_id] += 1
            item.id = f"{prefix}-{item.linked_topic_id}-{counts[item.linked_topic_id]}"
            result.append(item)
        return result

    def _literature(self, record):
        unique = {}
        for items in record.module_literature.values():
            for item in items:
                item["needs_verification"] = True
                unique[(item["category"], item["reference"], item.get("url"))] = item
        record.course.literature = [LiteratureItem(**item) for item in unique.values()]

    async def generate(self, project_id):
        async with self.lock(project_id):
            record = self.store.load(project_id)
            self.require_course(record)
            if record.course.status == "completed":
                return record.public()
            self.require_course(record, "approved")
            original = record.course.model_copy(deep=True)
            original_slide_modules = deepcopy(record.slide_modules)
            original_module_literature = deepcopy(record.module_literature)
            record.busy = "generating"
            record = self.store.save(record)
            deadline = time.monotonic() + self.settings.ml_timeout_seconds
            try:
                record.course.tests, record.course.seminars, record.course.lecture_slides = [], [], []
                record.slide_modules = {}
                record.module_literature = {}
                for module in record.course.modules:
                    bundle = await self.call(record, "content", self._subset(original, module), timeout=deadline-time.monotonic())
                    record.course.tests.extend(self._named_items(bundle.tests, "Q"))
                    record.course.seminars.extend(self._named_items(bundle.seminars, "SEM"))
                    for slide in bundle.lecture_slides:
                        slide = slide.model_copy(deep=True)
                        slide.slide_number = len(record.course.lecture_slides) + 1
                        record.slide_modules[str(slide.slide_number)] = module.id
                        record.course.lecture_slides.append(slide)
                    record.module_literature[module.id] = [item.model_dump() for item in bundle.literature]
                self._literature(record)
                record.course.status = "completed"
                await self.validate(record)
            except Exception:
                record.course = original
                record.slide_modules = original_slide_modules
                record.module_literature = original_module_literature
                record.busy = None
                self.store.save(record)
                raise
            record.busy = None
            return self.store.save(record).public()

    async def regenerate(self, project_id, request: RegeneratePartRequest):
        async with self.lock(project_id):
            record = self.store.load(project_id)
            self.require_course(record, "completed")
            if request.revision is not None and request.revision != record.revision:
                raise BackendError(409, "revision_conflict", "Загрузите свежую версию проекта", current_revision=record.revision)
            original = record.course.model_copy(deep=True)
            if request.element_type == "topic":
                target = next(((mod, topic) for mod in original.modules for topic in mod.topics if topic.id == request.element_id), None)
            else:
                target = next((question for question in original.tests if question.id == request.element_id), None)
            if target is None:
                raise BackendError(404, "element_not_found", "Тема или вопрос не найдены")
            changed = await self.call(record, "regenerate", original.model_copy(deep=True), request.element_type, request.element_id, request.instruction)
            if request.element_type == "test":
                candidate = next(item for item in changed.tests if item.id == request.element_id)
                current = next(item for item in record.course.tests if item.id == request.element_id)
                current.question, current.options, current.correct_answer = candidate.question, candidate.options, candidate.correct_answer
            else:
                module, old_topic = target
                candidate = next(topic for mod in changed.modules for topic in mod.topics if topic.id == request.element_id)
                current = next(topic for mod in record.course.modules for topic in mod.topics if topic.id == request.element_id)
                current.title, current.content_bullets, current.practice_description = candidate.title, candidate.content_bullets, candidate.practice_description
                updated_module = next(mod for mod in record.course.modules if mod.id == module.id)
                bundle = await self.call(record, "content", self._subset(record.course, updated_module))
                record.course.tests = [item for item in record.course.tests if item.linked_topic_id != old_topic.id] + self._named_items([item for item in bundle.tests if item.linked_topic_id == old_topic.id], "Q")
                record.course.seminars = [item for item in record.course.seminars if item.linked_topic_id != old_topic.id] + self._named_items([item for item in bundle.seminars if item.linked_topic_id == old_topic.id], "SEM")
                kept = [slide for slide in record.course.lecture_slides if record.slide_modules.get(str(slide.slide_number)) != module.id]
                free_numbers = [slide.slide_number for slide in record.course.lecture_slides if record.slide_modules.get(str(slide.slide_number)) == module.id]
                next_number = max((slide.slide_number for slide in record.course.lecture_slides), default=0) + 1
                record.slide_modules = {str(slide.slide_number): record.slide_modules[str(slide.slide_number)] for slide in kept}
                for index, slide in enumerate(bundle.lecture_slides):
                    slide = slide.model_copy(deep=True)
                    slide.slide_number = free_numbers[index] if index < len(free_numbers) else next_number + index - len(free_numbers)
                    kept.append(slide)
                    record.slide_modules[str(slide.slide_number)] = module.id
                record.course.lecture_slides = kept
                record.module_literature[module.id] = [item.model_dump() for item in bundle.literature]
                self._literature(record)
            await self.validate(record)
            return self.store.save(record).public()
