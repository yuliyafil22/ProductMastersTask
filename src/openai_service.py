import os
import logging
from openai import OpenAI, OpenAIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from src.schemas import EmailExtractionSchema

logger = logging.getLogger(__name__)

class OpenAIService:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-4o-mini"

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(OpenAIError),
        reraise=True
    )
    def extract_email_data(self, email_body: str) -> EmailExtractionSchema:
        system_prompt = (
            "Ты — квалифицированный ассистент по разбору входящей корреспонденции.\n"
            "Твоя задача — извлечь структурированные данные из письма.\n"
            "ПРАВИЛА:\n"
            "1. Извлекай контактные данные ТОЛЬКО автора письма (из обращения или подписи).\n"
            "2. Игнорируй телефоны систем поддержки, указанные в юридических дисклеймерах или футерах.\n"
            "3. Если письмо является спамом или автоматической рассылкой, ставь 'Spam/Irrelevant' и Urgency 'Low'."
        )

        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Текст письма:\n{email_body}"}
            ],
            response_format=EmailExtractionSchema,
            temperature=0.0  # Детерминированный вывод
        )

        return completion.choices[0].message.parsed