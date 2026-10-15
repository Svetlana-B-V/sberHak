import json
from pathlib import Path
from typing import Dict, Any
from ml.schemas import CourseProgram, ModuleItem, TopicItem, CompetencyItem
from ml.llm_client import llm_client

KB_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge_base.json"
with open(KB_PATH, "r", encoding="utf-8") as f:
    KNOWLEDGE_BASE = json.load(f)


def recalculate_and_balance_hours(course_dict: Dict[str, Any], target_total_hours: int) -> Dict[str, Any]:
    """
    ДЕТЕРМИНИРОВАННЫЙ БАЛАНСИРОВЩИК ЧАСОВ (0% ошибок в арифметике!).
    1. Фиксирует часы на Итоговую аттестацию (ia_hours).
    2. Пропорционально масштабирует часы тем под (target_total_hours - ia_hours).
    3. Выравнивает округление до часа через СРС последней темы.
    4. Строго пересчитывает суммы модулей снизу вверх (Topic -> Module -> Course).
    """
    tpl = course_dict.get("template_type", "dpp_pk")
    ia_hours = course_dict.get("ia_hours", 2 if tpl == "dpp_pk" else 6)
    if target_total_hours <= 24 and ia_hours > 4:
        ia_hours = 4
    course_dict["ia_hours"] = ia_hours
    course_dict["total_hours"] = target_total_hours

    study_hours_budget = max(4, target_total_hours - ia_hours)

    modules = course_dict.get("modules", [])
    all_topics = []
    for m in modules:
        for t in m.get("topics", []):
            t_sum = int(t.get("lecture_hours", 0)) + int(t.get("practice_hours", 0)) + int(t.get("lab_hours", 0)) + int(t.get("srs_hours", 0))
            if t_sum <= 0:
                t["srs_hours"] = 4
                t_sum = 4
            t["total_hours"] = t_sum
            all_topics.append(t)

    if not all_topics:
        return course_dict

    current_study_sum = sum(t["total_hours"] for t in all_topics)

    # Масштабируем каждую тему под целевой бюджет часов
    if current_study_sum != study_hours_budget and current_study_sum > 0:
        ratio = study_hours_budget / current_study_sum
        for t in all_topics:
            t["lecture_hours"] = max(0, round(int(t.get("lecture_hours", 0)) * ratio))
            t["practice_hours"] = max(0, round(int(t.get("practice_hours", 0)) * ratio))
            t["lab_hours"] = max(0, round(int(t.get("lab_hours", 0)) * ratio))
            t["srs_hours"] = max(1, round(int(t.get("srs_hours", 0)) * ratio))
            t["total_hours"] = t["lecture_hours"] + t["practice_hours"] + t["lab_hours"] + t["srs_hours"]

    # Точная компенсация погрешности округления (до 1 часа)
    new_study_sum = sum(t["total_hours"] for t in all_topics)
    diff = study_hours_budget - new_study_sum
    if diff != 0:
        # Корректируем часы в последних темах
        idx = len(all_topics) - 1
        while diff != 0 and idx >= 0:
            t = all_topics[idx]
            if diff > 0:
                t["srs_hours"] += diff
                t["total_hours"] += diff
                diff = 0
            else:
                # Нужно уменьшить часы
                can_reduce_srs = max(0, t["srs_hours"] - 1)
                reduce_amt = min(abs(diff), can_reduce_srs)
                t["srs_hours"] -= reduce_amt
                t["total_hours"] -= reduce_amt
                diff += reduce_amt
                if diff < 0 and t["practice_hours"] > 0:
                    red_pr = min(abs(diff), t["practice_hours"])
                    t["practice_hours"] -= red_pr
                    t["total_hours"] -= red_pr
                    diff += red_pr
            idx -= 1

    # Строгий пересчет итогов по каждому модулю снизу вверх
    for m in modules:
        m["lecture_hours"] = sum(int(t["lecture_hours"]) for t in m.get("topics", []))
        m["practice_hours"] = sum(int(t["practice_hours"]) for t in m.get("topics", []))
        m["lab_hours"] = sum(int(t["lab_hours"]) for t in m.get("topics", []))
        m["srs_hours"] = sum(int(t["srs_hours"]) for t in m.get("topics", []))
        m["total_hours"] = m["lecture_hours"] + m["practice_hours"] + m["lab_hours"] + m["srs_hours"]

    course_dict["duration_days"] = max(5, round(target_total_hours / 4))
    return course_dict


SKELETON_SYSTEM_PROMPT = f"""
Ты — Навык «Архитектор образовательных программ АЦР» (GigaCowork Skill #2).
На основе запроса методиста создай каркас образовательной программы.
Используй ТОЛЬКО реальные профессиональные стандарты из следующего реестра Минтруда РФ:
{json.dumps(KNOWLEDGE_BASE['profstandards'], ensure_ascii=False, indent=2)}

Если ни один профстандарт из реестра не подходит, укажи наиболее близкий и установи поле "needs_verification": true.
Каждая тема в модулях должна ссылаться хотя бы на одну компетенцию в поле "linked_competencies" (например, ["ПК-1"]).
"""


def generate_course_skeleton(project_id: str, user_query: str, template_type: str, total_hours: int, clarifications: str = "") -> CourseProgram:
    fallback_skeleton = {
        "project_id": project_id,
        "status": "skeleton_ready",
        "template_type": template_type,
        "title": "Анализ данных на Python и прикладные инструменты ИИ" if "python" in user_query.lower() or "анализ" in user_query.lower() else f"Образовательная программа: {user_query[:60]}",
        "annotation": "Программа направлена на формирование практических компетенций в области обработки данных, построения аналитических пайплайнов и применения современных ИТ-инструментов для решения прикладных задач бизнеса.",
        "goal": "Совершенствование и формирование новых профессиональных компетенций в области анализа данных, проектирования аналитических решений и автоматизации процессов принятия решений.",
        "tasks": [
            "Сформировать навык сбора, очистки и исследовательского анализа данных (EDA) на языке Python.",
            "Обучить методам построения аналитических витрин, визуализации метрик и проверки статистических гипотез.",
            "Развить практическое умение автоматизировать отчетность и внедрять модели анализа данных в бизнес-процессы."
        ],
        "target_audience": "Специалисты банковского и корпоративного сектора, аналитики и ИТ-специалисты, имеющие базовые навыки работы с табличными данными.",
        "education_form": "Очно-заочная с применением электронного обучения и дистанционных образовательных технологий (ЭО и ДОТ)",
        "total_hours": total_hours,
        "ia_hours": 2 if template_type == "dpp_pk" else 6,
        "ia_form": "Защита итогового аналитического проекта (зачёт)" if template_type == "dpp_pk" else "Защита командного проекта в формате очного хакатона",
        "duration_days": max(5, round(total_hours / 4)),
        "issued_document": "Удостоверение о повышении квалификации установленного образца" if template_type == "dpp_pk" else "Сертификат об освоении программы",
        "competencies": [
            {
                "id": "ПК-1",
                "activity_type": "Сбор, обработка и исследовательский анализ массивов данных",
                "name": "Способность выполнять подготовку, очистку и агрегацию корпоративных данных с использованием языка Python и специализированных библиотек",
                "profstandard_code": "06.035 «Специалист по большим данным» (Приказ Минтруда России от 06.07.2020 № 405н)",
                "labor_function_code": "A/01.6",
                "needs_verification": False,
                "practical_experience": [
                    "Загрузка и объединение разнородных источников данных (CSV, Excel, SQL)",
                    "Очистка пропусков, аномалий и дубликатов в транзакционных массивах"
                ],
                "skills": [
                    "Использовать библиотеки Pandas и NumPy для трансформации таблиц",
                    "Формулировать запросы для выборки и фильтрации данных"
                ],
                "knowledge": [
                    "Синтаксис и структуры данных языка Python 3.10+",
                    "Методы предобработки, агрегации и нормализации табличных данных"
                ]
            },
            {
                "id": "ПК-2",
                "activity_type": "Проектирование аналитических решений и проверка гипотез",
                "name": "Способность проводить статистический анализ, строить визуализации и презентовать аналитические выводы бизнесу",
                "profstandard_code": "06.015 «Специалист по информационным системам» (Приказ Минтруда России от 13.07.2023 № 586н)",
                "labor_function_code": "C/14.6",
                "needs_verification": False,
                "practical_experience": [
                    "Построение интерактивных дашбордов и графиков распределения метрик",
                    "Валидация продуктовых и финансовых гипотез на исторических данных"
                ],
                "skills": [
                    "Визуализировать данные с помощью Matplotlib, Seaborn и Plotly",
                    "Рассчитывать ключевые бизнес-метрики и интерпретировать результаты для заказчика"
                ],
                "knowledge": [
                    "Основы математической статистики и A/B-тестирования",
                    "Принципы визуализации данных и оформления аналитических отчетов"
                ]
            }
        ],
        "modules": [
            {
                "id": "1",
                "title": "Модуль 1. Инструментарий аналитика и обработка данных на Python",
                "total_hours": 34,
                "lecture_hours": 6,
                "practice_hours": 12,
                "lab_hours": 0,
                "srs_hours": 16,
                "attestation_form": "Тестирование",
                "topics": [
                    {
                        "id": "1.1",
                        "title": "Среда разработки Jupyter, базовые структуры Python и работа с файлами",
                        "total_hours": 10,
                        "lecture_hours": 2,
                        "practice_hours": 4,
                        "lab_hours": 0,
                        "srs_hours": 4,
                        "control_form": "Текущий контроль",
                        "linked_competencies": ["ПК-1"],
                        "content_bullets": [
                            "Настройка окружения Python, работа в JupyterLab и VS Code",
                            "Типы данных, списки, словари, функции и обработка исключений при чтении файлов"
                        ],
                        "practice_description": "Практикум: Написание скрипта первичного парсинга и проверки банковских выписок в форматах CSV/JSON."
                    },
                    {
                        "id": "1.2",
                        "title": "Библиотека Pandas: индексация, фильтрация, очистка и объединение таблиц (JOIN/Merge)",
                        "total_hours": 14,
                        "lecture_hours": 2,
                        "practice_hours": 4,
                        "lab_hours": 0,
                        "srs_hours": 8,
                        "control_form": "Практическое задание",
                        "linked_competencies": ["ПК-1"],
                        "content_bullets": [
                            "Структуры Series и DataFrame, работа с типами данных и датами",
                            "Обработка пропущенных значений (NaN), дедубликация и выявление выбросов",
                            "Сводные таблицы (pivot_table), группировки (groupby) и слияние датасетов"
                        ],
                        "practice_description": "Практикум «Очистка кредитного портфеля»: объединение 3 витрин данных и формирование чистого датасета."
                    },
                    {
                        "id": "1.3",
                        "title": "Интеграция Python с базами данных SQL и автоматизация выгрузок",
                        "total_hours": 10,
                        "lecture_hours": 2,
                        "practice_hours": 4,
                        "lab_hours": 0,
                        "srs_hours": 4,
                        "control_form": "Тестирование",
                        "linked_competencies": ["ПК-1"],
                        "content_bullets": [
                            "Подключение к реляционным СУБД через SQLAlchemy",
                            "Чтение SQL-запросов напрямую в Pandas DataFrame и экспорт отчетов в Excel"
                        ],
                        "practice_description": "Практикум: Автоматическая сборка многостраничного Excel-отчета из SQL-базы."
                    }
                ]
            },
            {
                "id": "2",
                "title": "Модуль 2. Исследовательский анализ (EDA), визуализация и итоговый проект",
                "total_hours": 36,
                "lecture_hours": 6,
                "practice_hours": 12,
                "lab_hours": 0,
                "srs_hours": 18,
                "attestation_form": "Собеседование",
                "topics": [
                    {
                        "id": "2.1",
                        "title": "Исследовательский анализ данных (EDA) и проверка статистических гипотез",
                        "total_hours": 12,
                        "lecture_hours": 2,
                        "practice_hours": 4,
                        "lab_hours": 0,
                        "srs_hours": 6,
                        "control_form": "Практическое задание",
                        "linked_competencies": ["ПК-2"],
                        "content_bullets": [
                            "Описательные статистики, квантили, корреляционный анализ",
                            "Формулирование продуктовых и бизнес-гипотез, критерии Стьюдента и Манна-Уитни"
                        ],
                        "practice_description": "Практикум: Поиск факторов оттока клиентов банка на основе исторической выборки."
                    },
                    {
                        "id": "2.2",
                        "title": "Визуализация данных и построение аналитических дашбордов (Matplotlib, Seaborn, Plotly)",
                        "total_hours": 12,
                        "lecture_hours": 2,
                        "practice_hours": 4,
                        "lab_hours": 0,
                        "srs_hours": 6,
                        "control_form": "Собеседование",
                        "linked_competencies": ["ПК-2"],
                        "content_bullets": [
                            "Выбор типа графика под бизнес-задачу: распределения, тренды, воронки",
                            "Интерактивная визуализация в Plotly и оформление выводов по принципу Pyramid Principle"
                        ],
                        "practice_description": "Практикум: Создание интерактивного отчета по ключевым показателям подразделения."
                    },
                    {
                        "id": "2.3",
                        "title": "Подготовка и упаковка сквозного аналитического проекта",
                        "total_hours": 12,
                        "lecture_hours": 2,
                        "practice_hours": 4,
                        "lab_hours": 0,
                        "srs_hours": 6,
                        "control_form": "Предзащита",
                        "linked_competencies": ["ПК-1", "ПК-2"],
                        "content_bullets": [
                            "Сборка сквозного пайплайна от сырых данных до презентации бизнесу",
                            "Оформление аналитической записки в формате «Проблема -> Инсайт -> Действие»"
                        ],
                        "practice_description": "Самостоятельная работа над кейсом заказчика и подготовка защитной презентации."
                    }
                ]
            }
        ]
    }

    user_prompt = (
        f"Запрос методиста: {user_query}\n"
        f"Уточнения: {clarifications}\n"
        f"Шаблон: {template_type}, Общий объем: {total_hours} ак. часов.\n"
        f"Сгенерируй JSON каркаса по образцу структуры."
    )
    raw_skeleton = llm_client.generate_json(SKELETON_SYSTEM_PROMPT, user_prompt, fallback_data=fallback_skeleton)
    raw_skeleton["project_id"] = project_id
    raw_skeleton["template_type"] = template_type
    raw_skeleton["status"] = "skeleton_ready"

    # Прогоняем через детерминированный математический балансировщик часов!
    balanced_dict = recalculate_and_balance_hours(raw_skeleton, total_hours)
    return CourseProgram(**balanced_dict)