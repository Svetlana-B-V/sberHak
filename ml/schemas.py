from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class ClarifyResponse(BaseModel):
    is_complete: bool = Field(description="Достаточно ли данных для генерации каркаса")
    template_type: Literal["dpp_pk", "doop"] = Field(
        description="dpp_pk — Повышение квалификации (Приказ 499), doop — Общеразвивающая программа (Приказ 629)"
    )
    template_reason: str = Field(description="Обоснование выбора шаблона АЦР")
    extracted_params: dict = Field(description="Извлеченные параметры: тема, часы, аудитория, форма обучения, форма ИА")
    clarifying_questions: List[str] = Field(default_factory=list, description="Список уточняющих вопросов методисту (если чего-то не хватает)")


class CompetencyItem(BaseModel):
    id: str = Field(description="Код компетенции, например ПК-1")
    activity_type: str = Field(description="Вид деятельности")
    name: str = Field(description="Формулировка профессиональной компетенции")
    profstandard_code: str = Field(description="Код и название профстандарта (или пометка [Требует проверки методистом])")
    labor_function_code: str = Field(description="Код трудовой функции, например C/14.6")
    needs_verification: bool = Field(default=False, description="True, если профстандарт не из подтвержденного реестра")
    practical_experience: List[str] = Field(description="Практический опыт (навыки)")
    skills: List[str] = Field(description="Умения")
    knowledge: List[str] = Field(description="Знания")


class TopicItem(BaseModel):
    id: str = Field(description="Номер темы, например 1.1")
    title: str = Field(description="Наименование темы")
    total_hours: int = Field(description="Всего часов по теме")
    lecture_hours: int = Field(default=0, description="Лекции (ЛК)")
    practice_hours: int = Field(default=0, description="Практические занятия (ПР)")
    lab_hours: int = Field(default=0, description="Лабораторные работы (ЛБ)")
    srs_hours: int = Field(default=0, description="Самостоятельная работа (СРС)")
    control_form: str = Field(default="", description="Форма текущего контроля (Собеседование, Тест, Контрольная точка)")
    linked_competencies: List[str] = Field(description="Список ID компетенций (например ['ПК-1']), которые раскрывает тема")
    content_bullets: List[str] = Field(default_factory=list, description="Дидактические единицы и содержание темы")
    practice_description: str = Field(default="", description="Описание практикума или самостоятельной работы по теме")


class ModuleItem(BaseModel):
    id: str = Field(description="Номер модуля/раздела, например 1")
    title: str = Field(description="Наименование раздела/модуля")
    total_hours: int = Field(description="Трудоемкость модуля всего")
    lecture_hours: int = Field(default=0)
    practice_hours: int = Field(default=0)
    lab_hours: int = Field(default=0)
    srs_hours: int = Field(default=0)
    attestation_form: str = Field(default="Собеседование", description="Форма промежуточной аттестации")
    topics: List[TopicItem] = Field(default_factory=list)


class TestQuestion(BaseModel):
    id: str = Field(description="ID вопроса, например Q-1")
    question: str = Field(description="Текст тестового вопроса")
    options: List[str] = Field(description="4 варианта ответа")
    correct_answer: str = Field(description="Точный текст правильного ответа из списка options")
    linked_topic_id: str = Field(description="ID проверяемой темы, например 1.1")
    linked_competency_id: str = Field(description="ID проверяемой компетенции, например ПК-1")


class SeminarTask(BaseModel):
    id: str = Field(description="ID задания, например SEM-1")
    linked_topic_id: str = Field(description="ID темы, например 1.2")
    title: str = Field(description="Название практического задания / семинара")
    scenario: str = Field(description="Описание кейса и шагов выполнения")
    deliverables: List[str] = Field(description="Какие артефакты сдает слушатель")
    evaluation_criteria: List[str] = Field(description="Критерии оценки с разбалловкой (рубрики)")


class SlideItem(BaseModel):
    slide_number: int
    title: str
    bullets: List[str]
    speaker_notes: str


class LiteratureItem(BaseModel):
    category: Literal["normative", "main", "additional", "internet", "software"]
    reference: str
    url: Optional[str] = None
    needs_verification: bool = Field(default=False, description="Пометка, если источник не подтвержден в базе")


class ValidationReport(BaseModel):
    is_valid: bool
    hours_math_ok: bool
    competency_coverage_ok: bool
    completeness_ok: bool
    unverified_sources_count: int
    details: List[str]
    errors: List[str]
    metrics: dict = Field(default_factory=dict, description="Токены, время генерации, экономия часов методиста")


class CourseProgram(BaseModel):
    project_id: str
    status: Literal["clarifying", "skeleton_ready", "approved", "completed"] = "clarifying"
    template_type: Literal["dpp_pk", "doop"] = "dpp_pk"
    title: str
    annotation: str
    goal: str
    tasks: List[str] = Field(default_factory=list)
    target_audience: str
    education_form: str = "Очно-заочная с применением ЭО и ДОТ"
    total_hours: int = 72
    ia_hours: int = 2
    ia_form: str = "Защита итогового проекта (зачёт)"
    duration_days: int = 18
    issued_document: str = "Удостоверение о повышении квалификации установленного образца"
    competencies: List[CompetencyItem] = Field(default_factory=list)
    modules: List[ModuleItem] = Field(default_factory=list)
    tests: List[TestQuestion] = Field(default_factory=list)
    seminars: List[SeminarTask] = Field(default_factory=list)
    lecture_slides: List[SlideItem] = Field(default_factory=list)
    literature: List[LiteratureItem] = Field(default_factory=list)
    validation_report: Optional[ValidationReport] = None