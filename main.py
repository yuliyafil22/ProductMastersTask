import os
import sys
import json
import logging
from typing import Optional, Literal, List
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from openai import OpenAI, OpenAIError

# ==========================================
# 0. НАСТРОЙКА ЛОГИРОВАНИЯ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ==========================================
# 1. БЕЗОПАСНОСТЬ И ПРОВЕРКА КЛЮЧЕЙ
# ==========================================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY or OPENAI_API_KEY == "sk-proj-your-actual-api-key-here":
    logger.critical(
        "ОШИБКА: OPENAI_API_KEY не найден или не настроен в файле .env!\n"
        "1. Создай файл .env в корне проекта.\n"
        "2. Добавь строку: OPENAI_API_KEY=sk-proj-твой-ключ\n"
        "Завершение работы скрипта."
    )
    sys.exit(1)

# Инициализация официального клиента OpenAI (v1.x+)
client = OpenAI(api_key=OPENAI_API_KEY)

# ==========================================
# 2. PYDANTIC-СХЕМА СТРУКТУРИРОВАННЫХ ДАННЫХ
# ==========================================
class EmailData(BaseModel):
    name: Optional[str] = Field(
        default=None,
        description="Имя и/или фамилия отправителя. Если явно не указаны — null."
    )
    phone: Optional[str] = Field(
        default=None,
        description="Номер телефона автора письма. Извлекай только номер отправителя, игнорируй системные телефоны из футеров."
    )
    subject: str = Field(
        description="Краткая емкая тема обращения (2-5 слов)."
    )
    urgency: Literal['Low', 'Medium', 'High'] = Field(
        description="Уровень срочности: High (сбой оплаты, брак, сарказм/жалоба), Medium (задержка доставки, стандартный запрос), Low (спам, общая информация)."
    )
    error_flag: bool = Field(
        description="Флаг True, если в сообщении есть проблемы с данными: отсутствует номер телефона, телефон написан прописью, сарказм, опечатки в номере или противоречивый контекст."
    )
    reasoning: str = Field(
        description="Краткое объяснение (1-2 предложения), почему выставлена именно такая срочность и извлечены эти данные."
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: Optional[str]) -> Optional[str]:
        if v and v.strip().lower() in ["unknown", "н/д", "не указано", "none", "null"]:
            return None
        return v.strip().title() if v else None


# ==========================================
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
INPUT_FILE = Path("data/input_emails.json")
OUTPUT_FILE = Path("results.xlsx")

def load_emails(file_path: Path) -> List[dict]:
    if not file_path.exists():
        logger.error(f"Файл {file_path} не найден! Создайте его и поместите датасет писем.")
        sys.exit(1)
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def parse_email_with_openai(email_body: str) -> EmailData:
    system_prompt = (
        "Ты — квалифицированный AI-ассистент клиентской поддержки e-commerce.\n"
        "Твоя задача — извлечь структурированные данные из письма с высокой точностью.\n"
        "ПРАВИЛА ИЗВЛЕЧЕНИЯ:\n"
        "1. Извлекай контактные данные (имя и телефон) ТОЛЬКО автора письма.\n"
        "2. Игнорируй номера телефонов из подписей компаний или системных уведомлений.\n"
        "3. Внимательно распознавай сарказм (например: 'Спасибо за быструю доставку, жду 3 недели') — это всегда urgency='High' и error_flag=True.\n"
        "4. Если номер телефона отсутствует, написан слова/прописью или с опечаткой — ставь phone=null и error_flag=True."
    )

    # Актуальный вызов Structured Outputs из SDK OpenAI v1.x+
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Текст входящего письма:\n{email_body}"}
        ],
        response_format=EmailData,
        temperature=0.0
    )

    return completion.choices[0].message.parsed


# ==========================================
# 4. ОСНОВНОЙ ЦИКЛ ОБРАБОТКИ И СОХРАНЕНИЕ
# ==========================================
def main():
    emails = load_emails(INPUT_FILE)
    logger.info(f"Загружено {len(emails)} писем из {INPUT_FILE}. Начинаем обработку...")

    results = []

    for idx, item in enumerate(emails, 1):
        email_id = item.get("id", f"MSG-{idx:03d}")
        email_body = item.get("body", "")

        logger.info(f"[{idx}/{len(emails)}] Обработка письма {email_id}...")

        try:
            # Безопасный вызов OpenAI API
            extracted_data: EmailData = parse_email_with_openai(email_body)

            results.append({
                "ID": email_id,
                "Name": extracted_data.name or "Не указано",
                "Phone": extracted_data.phone or "Отсутствует",
                "Subject": extracted_data.subject,
                "Urgency": extracted_data.urgency,
                "Error Flag": extracted_data.error_flag,
                "Reasoning": extracted_data.reasoning,
                "Status": "Успешно"
            })

        except OpenAIError as e:
            logger.error(f"Ошибка OpenAI API при обработке письма {email_id}: {str(e)}")
            results.append({
                "ID": email_id,
                "Name": "ОШИБКА",
                "Phone": "ОШИБКА",
                "Subject": "Ошибка API",
                "Urgency": "High",
                "Error Flag": True,
                "Reasoning": f"OpenAI API Error: {str(e)}",
                "Status": "Сбой API"
            })
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при обработке письма {email_id}: {str(e)}")
            results.append({
                "ID": email_id,
                "Name": "ОШИБКА",
                "Phone": "ОШИБКА",
                "Subject": "Системная ошибка",
                "Urgency": "High",
                "Error Flag": True,
                "Reasoning": f"System Error: {str(e)}",
                "Status": "Сбой обработки"
            })

    # Сохранение в Excel с помощью Pandas и openpyxl
    logger.info("Формирование Excel-файла с результатами...")
    df = pd.DataFrame(results)

    try:
        df.to_excel(OUTPUT_FILE, index=False, engine="openpyxl")
        logger.info(f"Успешно! Все данные сохранены в файл: {OUTPUT_FILE.resolve()}")
    except Exception as e:
        logger.critical(f"Ошибка при сохранении Excel-файла: {str(e)}")


if __name__ == "__main__":
    main()