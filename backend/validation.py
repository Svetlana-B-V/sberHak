"""Backend invariants; domain content quality remains the ML team's responsibility."""

from collections import Counter
import re

from backend.errors import BackendError
from ml.schemas import CourseProgram, ClarifyResponse


HOUR_FIELDS = ("lecture_hours", "practice_hours", "lab_hours", "srs_hours")


def check_clarifications(analysis: ClarifyResponse, text: str) -> ClarifyResponse:
    value = analysis.model_copy(deep=True)
    query = text.lower()
    required = [
        (bool(re.search(r"повышени\w*\s+квалификац|стажиров|\bдпп\b|общеразвива|\bдооп\b", query)), "Какой тип программы нужен: повышение квалификации или общеразвивающая программа?"),
        (bool(re.search(r"\d+\s*(?:час|ч\b|ак\.?\s*ч)", query)), "Какой точный объём программы в академических часах?"),
        (bool(re.search(r"для\s|школьник|студент|сотрудник|специалист|учител|слушател", query)), "Кто будет учиться и какой у слушателей входной уровень?"),
        (bool(re.search(r"очн|заочн|дистанцион|онлайн", query)), "Какая форма обучения нужна: очная, заочная или очно-заочная?"),
        (bool(re.search(r"аттестац|защит|экзамен|зач[её]т|итогов\w*\s+тест|портфолио", query)), "В какой форме будет итоговая аттестация?"),
    ]
    questions = [question for present, question in required if not present]
    if not required[1][0]:
        value.extracted_params.pop("total_hours", None)
    value.clarifying_questions = questions if questions else value.clarifying_questions[:5]
    value.is_complete = not value.clarifying_questions
    return value


def check_course(course: CourseProgram, completed: bool = False) -> None:
    errors = []
    if course.total_hours < 1 or not 0 <= course.ia_hours < course.total_hours:
        errors.append("Объём должен быть положительным, а часы ИА меньше общего объёма.")
    if not course.modules or not course.competencies or not course.title.strip() or not course.goal.strip():
        errors.append("Не заполнены название, цель, компетенции или модули.")
    comp_ids = [comp.id for comp in course.competencies]
    topic_ids = [topic.id for mod in course.modules for topic in mod.topics]
    for name, ids in [("модулей", [mod.id for mod in course.modules]), ("тем", topic_ids), ("компетенций", comp_ids)]:
        if len(ids) != len(set(ids)) or any(not key.strip() for key in ids):
            errors.append(f"Идентификаторы {name} должны быть непустыми и уникальными.")
    known_comp = set(comp_ids)
    coverage = set()
    for mod in course.modules:
        if not mod.title.strip():
            errors.append(f"Модуль {mod.id}: не заполнено название.")
        if not mod.topics:
            errors.append(f"Модуль {mod.id} не содержит тем.")
        for topic in mod.topics:
            if not topic.title.strip():
                errors.append(f"Тема {topic.id}: не заполнено название.")
            values = [getattr(topic, name) for name in HOUR_FIELDS]
            if any(value < 0 for value in values) or topic.total_hours < 0 or sum(values) != topic.total_hours:
                errors.append(f"Тема {topic.id}: неверная арифметика или отрицательные часы.")
            if not topic.linked_competencies or not set(topic.linked_competencies) <= known_comp:
                errors.append(f"Тема {topic.id}: некорректные связи с компетенциями.")
            coverage.update(topic.linked_competencies)
        for name in (*HOUR_FIELDS, "total_hours"):
            if getattr(mod, name) != sum(getattr(topic, name) for topic in mod.topics):
                errors.append(f"Модуль {mod.id}: не сходится {name}.")
    if sum(mod.total_hours for mod in course.modules) + course.ia_hours != course.total_hours:
        errors.append("Сумма часов модулей и ИА не равна общему объёму.")
    if known_comp - coverage:
        errors.append("Не все компетенции раскрыты в темах.")
    if completed:
        topic_map = {topic.id: topic for mod in course.modules for topic in mod.topics}
        assessments = Counter()
        for question in course.tests:
            if not question.question.strip() or any(not option.strip() for option in question.options):
                errors.append(f"Вопрос {question.id}: пустой текст или вариант ответа.")
            if question.linked_topic_id not in topic_map or question.linked_competency_id not in known_comp:
                errors.append(f"Вопрос {question.id}: ссылка на неизвестную тему или компетенцию.")
            elif question.linked_competency_id not in topic_map[question.linked_topic_id].linked_competencies:
                errors.append(f"Вопрос {question.id}: компетенция не связана с указанной темой.")
            if len(question.options) < 2 or len(question.options) != len(set(question.options)) or question.options.count(question.correct_answer) != 1:
                errors.append(f"Вопрос {question.id}: неверные варианты ответа или ключ.")
            assessments[question.linked_competency_id] += 1
        for task in course.seminars:
            if task.linked_topic_id not in topic_map or not task.scenario.strip() or not task.evaluation_criteria:
                errors.append(f"Семинар {task.id}: не заполнено задание, критерии или связь с темой.")
            else:
                assessments.update(topic_map[task.linked_topic_id].linked_competencies)
        if any(assessments[key] < 2 for key in known_comp):
            errors.append("Каждой компетенции нужны минимум два оценочных средства.")
        for name, items in [("вопросов", course.tests), ("семинаров", course.seminars)]:
            if len({item.id for item in items}) != len(items):
                errors.append(f"Повторяются идентификаторы {name}.")
        if not course.tests or not course.seminars or not course.lecture_slides:
            errors.append("Не заполнены тесты, семинары или слайды.")
    if errors:
        raise BackendError(422, "course_validation_failed", "Программа не прошла проверку бэкенда", errors=errors)


def mark_unverified_sources(course: CourseProgram) -> None:
    # A domain allow-list is not evidence that a particular publication exists.
    for item in course.literature:
        item.needs_verification = True
    for comp in course.competencies:
        if course.template_type == "doop":
            comp.profstandard_code = ""
            comp.labor_function_code = ""
            comp.needs_verification = False
        else:
            comp.needs_verification = True
