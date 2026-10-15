import json
from pathlib import Path
from ml.schemas import CourseProgram, TestQuestion, SeminarTask, SlideItem, LiteratureItem
from ml.llm_client import llm_client

KB_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge_base.json"
with open(KB_PATH, "r", encoding="utf-8") as f:
    KNOWLEDGE_BASE = json.load(f)

CONTENT_SYSTEM_PROMPT = """
Ты — Навык «Разработчик учебно-методических материалов АЦР» (GigaCowork Skill #3).
На основе утвержденного методистом каркаса программы сгенерируй полный комплект материалов:
1. "tests": минимум по 2 тестовых вопроса на каждую тему (с 4 вариантами ответа, точным правильным ответом и привязкой к linked_topic_id и linked_competency_id).
2. "seminars": практические задания для семинаров с критериями оценки (разбалловка 0-25, 26-35, 36-40 баллов).
3. "lecture_slides": план и содержание слайдов презентации для Модуля 1 (минимум 6 слайдов с буллитами и заметками спикера).
4. "literature": нормативно-правовые акты, основная и дополнительная литература, ПО.
"""


def generate_full_course_content(course: CourseProgram) -> CourseProgram:
    # Собираем все ID тем и компетенций из утвержденного каркаса, чтобы гарантировать 100% покрытие!
    fallback_tests = []
    fallback_seminars = []
    q_counter = 1
    sem_counter = 1

    for mod in course.modules:
        for topic in mod.topics:
            comp_id = topic.linked_competencies[0] if topic.linked_competencies else (course.competencies[0].id if course.competencies else "ПК-1")
            fallback_tests.append({
                "id": f"Q-{q_counter}",
                "question": f"Какой метод или подход является ключевым при решении задач в рамках темы «{topic.title}»?",
                "options": [
                    "Использование воспроизводимых скриптов и валидации структуры входных данных",
                    "Ручное редактирование исходных файлов без сохранения истории изменений",
                    "Удаление всех строк с числовыми значениями без предварительного анализа",
                    "Отказ от использования документации и спецификаций"
                ],
                "correct_answer": "Использование воспроизводимых скриптов и валидации структуры входных данных",
                "linked_topic_id": topic.id,
                "linked_competency_id": comp_id
            })
            q_counter += 1

            fallback_seminars.append({
                "id": f"SEM-{sem_counter}",
                "linked_topic_id": topic.id,
                "title": f"Практикум по теме {topic.id}: «{topic.title}»",
                "scenario": topic.practice_description or f"Выполните практическую разработку и анализ кейса по теме «{topic.title}» на предоставленном наборе данных.",
                "deliverables": [
                    "Исполняемый код / ноутбук с комментариями или аналитический артефакт",
                    "Краткое резюме выводов: «Проблема -> Инсайт -> Действие»"
                ],
                "evaluation_criteria": [
                    "Полнота и корректность выполнения всех шагов задания (0–40 баллов)",
                    "Обоснованность выбранных инструментов и чистота оформления (0–30 баллов)",
                    "Практическая применимость выводов и защита результата (0–30 баллов). Зачёт от 70 баллов."
                ]
            })
            sem_counter += 1

    first_mod_title = course.modules[0].title if course.modules else course.title
    fallback_slides = [
        {
            "slide_number": 1,
            "title": f"{course.title} — {first_mod_title}",
            "bullets": [
                f"Объем программы: {course.total_hours} ак. ч.",
                f"Целевая аудитория: {course.target_audience}",
                "Формат работы: теория + практические кейсы + сквозной проект"
            ],
            "speaker_notes": "Приветствие слушателей, знакомство с регламентом курса и требованиями к итоговой аттестации."
        },
        {
            "slide_number": 2,
            "title": "Цели модуля и формируемые компетенции",
            "bullets": [c.name for c in course.competencies[:3]] or ["Освоение практических инструментов по теме курса"],
            "speaker_notes": "Объяснить связь между темами модуля, трудовыми функциями профстандарта и задачами реального бизнеса."
        }
    ]
    for idx, t in enumerate(course.modules[0].topics if course.modules else [], start=3):
        fallback_slides.append({
            "slide_number": idx,
            "title": f"Тема {t.id}. {t.title}",
            "bullets": t.content_bullets if t.content_bullets else [
                f"Трудоемкость: {t.total_hours} ч. (ЛК: {t.lecture_hours}, ПР: {t.practice_hours}, СРС: {t.srs_hours})",
                t.practice_description or "Практическая отработка навыков на реальном наборе данных"
            ],
            "speaker_notes": f"Разобрать ключевые понятия темы {t.id} и показать демонстрационный пример перед переходом к практикуму."
        })

    reg_list = KNOWLEDGE_BASE["regulations"].get(course.template_type, KNOWLEDGE_BASE["regulations"]["dpp_pk"])
    fallback_literature = [
        {"category": "normative", "reference": reg, "url": "https://www.consultant.ru/", "needs_verification": False}
        for reg in reg_list
    ] + [
        {"category": "main", "reference": "Маккинни У. Python и анализ данных: первичная обработка данных с применением pandas, NumPy и Jupyter. — М.: ДМК Пресс, 2023.", "url": "https://pandas.pydata.org/", "needs_verification": False},
        {"category": "main", "reference": "Жерон О. Прикладное машинное обучение с помощью Scikit-Learn, Keras и TensorFlow. — М.: Диалектика, 2022.", "url": "https://scikit-learn.org/", "needs_verification": False},
        {"category": "internet", "reference": "Официальная документация Python и библиотек анализа данных", "url": "https://docs.python.org/", "needs_verification": False},
        {"category": "internet", "reference": "Профессиональное ИТ-сообщество Habr — кейсы анализа данных и архитектуры", "url": "https://habr.com/", "needs_verification": False},
        {"category": "software", "reference": "Среда разработки VS Code / JupyterLab, Python 3.10+, Git (GitVerse)", "url": "https://gitverse.ru/", "needs_verification": False}
    ]

    fallback_bundle = {
        "tests": fallback_tests,
        "seminars": fallback_seminars,
        "lecture_slides": fallback_slides,
        "literature": fallback_literature
    }

    prompt = (
        f"Программа: {course.title} ({course.total_hours} ч.)\n"
        f"Компетенции: {json.dumps([c.model_dump() for c in course.competencies], ensure_ascii=False)}\n"
        f"Модули и темы: {json.dumps([m.model_dump() for m in course.modules], ensure_ascii=False)}\n"
        f"Сгенерируй полный пакет оценочных и учебных материалов."
    )
    generated = llm_client.generate_json(CONTENT_SYSTEM_PROMPT, prompt, fallback_data=fallback_bundle)

    course.tests = [TestQuestion(**q) for q in generated.get("tests", fallback_tests)]
    course.seminars = [SeminarTask(**s) for s in generated.get("seminars", fallback_seminars)]
    course.lecture_slides = [SlideItem(**sl) for sl in generated.get("lecture_slides", fallback_slides)]
    course.literature = [LiteratureItem(**lit) for lit in generated.get("literature", fallback_literature)]
    course.status = "completed"
    return course