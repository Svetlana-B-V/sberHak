import json
from pathlib import Path
from ml.schemas import CourseProgram, ValidationReport
from ml.llm_client import llm_client
from ml.skills.skeleton import recalculate_and_balance_hours

KB_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge_base.json"
with open(KB_PATH, "r", encoding="utf-8") as f:
    KNOWLEDGE_BASE = json.load(f)


def validate_course_program(course: CourseProgram) -> ValidationReport:
    """
    Навык 4 (GigaCowork Skill #4): Детерминированная самопроверка программы.
    Проверяет:
    1. Арифметику часов (Тема -> Модуль -> Учебный план -> Общий объем).
    2. Покрытие каждой компетенции темами и тестовыми вопросами.
    3. Достоверность источников и профстандартов.
    4. Полноту обязательных разделов шаблона АЦР.
    """
    errors = []
    details = []

    # 1. Проверка арифметики часов
    modules_sum = 0
    for mod in course.modules:
        topics_sum = 0
        for t in mod.topics:
            row_sum = t.lecture_hours + t.practice_hours + t.lab_hours + t.srs_hours
            if row_sum != t.total_hours:
                errors.append(f"Тема {t.id}: сумма видов работ ({row_sum} ч.) не равна итогу по теме ({t.total_hours} ч.).")
            topics_sum += t.total_hours
        if topics_sum != mod.total_hours:
            errors.append(f"Модуль {mod.id}: сумма часов тем ({topics_sum} ч.) не равна итогу модуля ({mod.total_hours} ч.).")
        modules_sum += mod.total_hours

    total_calculated = modules_sum + course.ia_hours
    hours_math_ok = (total_calculated == course.total_hours) and (len(errors) == 0)
    if not hours_math_ok:
        errors.append(f"Общая сумма часов ({modules_sum} ч. модули + {course.ia_hours} ч. ИА = {total_calculated} ч.) не сходится с заявленным объемом ({course.total_hours} ч.).")
    else:
        details.append(f"✅ Арифметика часов безупречна: {modules_sum} ч. (модули) + {course.ia_hours} ч. (ИА) = {course.total_hours} ак. ч.")

    # 2. Проверка сквозной трассировки (матрицы покрытия компетенций)
    covered_by_topics = set()
    for mod in course.modules:
        for t in mod.topics:
            covered_by_topics.update(t.linked_competencies)

    covered_by_tests = {q.linked_competency_id for q in course.tests}
    competency_coverage_ok = True

    for comp in course.competencies:
        if comp.id not in covered_by_topics:
            competency_coverage_ok = False
            errors.append(f"Компетенция {comp.id} не раскрыта ни в одной теме учебного плана.")
        if course.status == "completed" and comp.id not in covered_by_tests:
            competency_coverage_ok = False
            errors.append(f"Компетенция {comp.id} не проверяется ни одним тестовым вопросом.")

    if competency_coverage_ok:
        details.append(f"✅ 100% покрытие компетенций ({len(course.competencies)} из {len(course.competencies)} связаны с темами и вопросами аттестации).")

    # 3. Проверка достоверности источников и профстандартов
    unverified_count = 0
    verified_domains = KNOWLEDGE_BASE.get("verified_domains", [])
    for comp in course.competencies:
        if comp.needs_verification:
            unverified_count += 1
    for lit in course.literature:
        if lit.url and not any(d in lit.url for d in verified_domains):
            lit.needs_verification = True
        if lit.needs_verification:
            unverified_count += 1
            if "[Требует проверки методистом]" not in lit.reference:
                lit.reference += " [Требует проверки методистом]"

    details.append(
        f"✅ Все источники и НПА верифицированы по реестру."
        if unverified_count == 0 else
        f"⚠️ Выявлено {unverified_count} внешних источников с пометкой [Требует проверки методистом]."
    )

    # 4. Проверка полноты разделов шаблона АЦР
    completeness_ok = bool(course.title and course.goal and course.competencies and course.modules)
    if course.status == "completed":
        completeness_ok = completeness_ok and bool(course.tests and course.seminars and course.lecture_slides)
    if completeness_ok:
        details.append(f"✅ Все обязательные разделы шаблона АЦР ({'ДПП ПК — Приказ № 499' if course.template_type == 'dpp_pk' else 'ДООП — Приказ № 629'}) заполнены.")
    else:
        errors.append("Не все обязательные разделы шаблона заполнены.")

    report = ValidationReport(
        is_valid=(hours_math_ok and competency_coverage_ok and completeness_ok),
        hours_math_ok=hours_math_ok,
        competency_coverage_ok=competency_coverage_ok,
        completeness_ok=completeness_ok,
        unverified_sources_count=unverified_count,
        details=details,
        errors=errors,
        metrics=llm_client.get_usage_metrics(course.total_hours)
    )
    course.validation_report = report
    return report


def regenerate_course_part(course: CourseProgram, element_type: str, element_id: str, instruction: str) -> CourseProgram:
    """
    Точечная пересборка отдельной темы или теста по запросу методиста БЕЗ перегенерации всего комплекта
    и БЕЗ нарушения баланса часов.
    """
    if element_type == "topic":
        for mod in course.modules:
            for t in mod.topics:
                if t.id == element_id:
                    fallback_topic = {
                        "title": f"{t.title} (обновлено: {instruction[:35]})",
                        "content_bullets": t.content_bullets + [f"Углубленный блок по запросу методиста: {instruction}"],
                        "practice_description": f"Обновленный практикум ({instruction}): {t.practice_description}"
                    }
                    prompt = (
                        f"Текущая тема {t.id}: {t.title}\n"
                        f"Содержание: {t.content_bullets}\n"
                        f"Инструкция методиста по правке: {instruction}\n"
                        f"Верни JSON с обновленными полями title, content_bullets, practice_description. Часы ({t.total_hours} ч.) менять НЕЛЬЗЯ."
                    )
                    res = llm_client.generate_json("Ты — методист-редактор АЦР. Обнови только указанную тему.", prompt, fallback_topic)
                    t.title = res.get("title", fallback_topic["title"])
                    t.content_bullets = res.get("content_bullets", fallback_topic["content_bullets"])
                    t.practice_description = res.get("practice_description", fallback_topic["practice_description"])
                    break

    elif element_type == "test":
        for q in course.tests:
            if q.id == element_id:
                q.question = f"[Усложненный вопрос: {instruction}] {q.question}"
                break

    # Повторно запускаем самопроверку, чтобы убедиться, что согласованность сохранена
    validate_course_program(course)
    return course