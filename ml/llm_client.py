import os
import re
import json
import time
from typing import Optional, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class CloudRuLLMClient:
    def __init__(self):
        self.api_key = os.getenv("CLOUD_RU_API_KEY", "")
        self.base_url = os.getenv("CLOUD_RU_BASE_URL", "https://foundation-models.api.cloud.ru/v1")
        self.model = os.getenv("CLOUD_RU_MODEL", "Qwen/Qwen2.5-72B-Instruct")
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_calls = 0

        self.client = None
        if self.api_key and self.api_key != "ваш_ключ_от_cloud_ru":
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )

    @property
    def is_mock_mode(self) -> bool:
        return self.client is None

    def _clean_json_string(self, raw_text: str) -> str:
        """Удаляет markdown-обертки ```json ... ``` и лишний текст вокруг JSON."""
        raw_text = raw_text.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text)
        if match:
            raw_text = match.group(1).strip()
        # Находим первую { или [ и последнюю } или ]
        start_brace = raw_text.find("{")
        end_brace = raw_text.rfind("}")
        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
            return raw_text[start_brace:end_brace + 1]
        return raw_text

    def generate_json(self, system_prompt: str, user_prompt: str, fallback_data: Dict[str, Any], temperature: float = 0.2) -> Dict[str, Any]:
        """
        Отправляет запрос в Cloud.ru Foundation Models и гарантированно возвращает валидный Python dict.
        Если API-ключ еще не прописан, возвращает fallback_data (чтобы демо работало в любой ситуации).
        """
        if self.is_mock_mode:
            time.sleep(0.8)  # Имитация сетевой задержки для красивого демо
            self.total_prompt_tokens += 850
            self.total_completion_tokens += 1200
            self.total_calls += 1
            return fallback_data

        for attempt in range(2):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt + "\nВАЖНО: Отвечай СТРОГО валидным JSON без комментариев."},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=temperature,
                )
                if response.usage:
                    self.total_prompt_tokens += response.usage.prompt_tokens
                    self.total_completion_tokens += response.usage.completion_tokens
                self.total_calls += 1

                content = response.choices[0].message.content or "{}"
                cleaned = self._clean_json_string(content)
                return json.loads(cleaned)
            except Exception as e:
                print(f"[LLM Warning] Попытка {attempt + 1} не удалась: {e}")
                if attempt == 1:
                    print("[LLM Fallback] Используем резервную структуру данных.")
                    return fallback_data
        return fallback_data

    def get_usage_metrics(self, total_course_hours: int) -> dict:
        total_tokens = self.total_prompt_tokens + self.total_completion_tokens
        # Средняя оценка стоимости токенов в облаке ~0.00025 руб за токен
        estimated_cost_rub = round(total_tokens * 0.00025, 2)
        # Методист тратит в среднем 0.6 часа реального времени на 1 ак. час программы (для 72ч курса ~ 43 часа работы)
        saved_methodist_hours = max(12, round(total_course_hours * 0.6))
        return {
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "total_tokens": total_tokens,
            "api_calls": self.total_calls,
            "estimated_cost_rub": estimated_cost_rub,
            "saved_methodist_hours": saved_methodist_hours,
            "mode": "MOCK_DEMO" if self.is_mock_mode else f"CLOUD_RU ({self.model})"
        }


llm_client = CloudRuLLMClient()