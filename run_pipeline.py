import json
import logging
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Any

from pydantic import BaseModel, ValidationError, Field

# Импортируем функцию обработки и настройку OpenAI из нашего основного модуля
from main import parse_email_with_openai, EmailData, OUTPUT_FILE, OPENAI_API_KEY
import pandas as pd

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("PipelineRunner")

INPUT_FILE = Path("data/input_emails.json")


# ==========================================
# 1. СХЕМА ВАЛИДАЦИИ ВХОДЯЩЕГО JSON
# ==========================================
class InputEmailSchema(BaseModel):
    """Схема проверки корректности структуры каждого письма в JSON."""
    id: str = Field(..., min_length=1, description="Уникальный идентификатор письма")
    subject: str = Field(..., description="Заголовок письма")
    body: str = Field(..., min_length=1, description="Текст письма")
    edge_case_note: str = Field(default="", description="Заметка о краевом случае (опционально)")


# ==========================================
# 2. ЗАГРУЗКА И ВАЛИДАЦИЯ ФАЙЛА
# ==========================================
def load_and_validate_dataset(file_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Загружает JSON и валидирует каждое письмо.
    Возвращает кортеж: (валидные_письма, поврежденные_записи)
    """
    if not file_path.exists():
        logger.critical(f"Файл датасета {file_path.resolve()} не найден!")
        sys.exit(1)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except json.JSONDecodeError as e:
        logger.critical(f"Ошибка чтения JSON-файла: {str(e)}")
        sys.exit(1)

    if not isinstance(raw_data, list):
        logger.critical("Входящий JSON должен содержать СПИСОК объектов.")
        sys.exit(1)

    valid_emails = []
    corrupted_emails = []

    for index, item in enumerate(raw_data, start=1):
        try:
            # Валидация через Pydantic
            validated_item = InputEmailSchema(**item)
            valid_emails.append(validated_item.model_dump())
        except ValidationError as ve:
            logger.warning(f"Запись #{index} не прошла валидацию: {ve.errors()}")
            corrupted_emails.append({
                "raw_item": item,
                "errors": ve.errors()
            })

    logger.info(
        f"Проверка завершена: Найдено {len(valid_emails)} валидных писем и {len(corrupted_emails)} ошибочных записей.")
    return valid_emails, corrupted_emails


# ==========================================
# 3. АВТОМАТИЧЕСКИЙ ЗАПУСК ПАЙПЛАЙНА
# ==========================================
def run_automation():
    logger.info("=== ЗАПУСК АВТОМАТИЗИРОВАННОГО ПАЙПЛАЙНА ОБРАБОТКИ ===")

    # 1. Загрузка и валидация датасета
    emails, corrupted = load_and_validate_dataset(INPUT_FILE)

    if not emails:
        logger.error("Нет валидных писем для обработки. Завершение работы.")
        return

    results = []

    # 2. Обработка через OpenAI API (gpt-4o-mini)
    for idx, email in enumerate(emails, start=1):
        email_id = email["id"]
        body = email["body"]

        logger.info(f"[{idx}/{len(emails)}] Пакетная обработка письма: {email_id}")

        try:
            # Вызов функции из main.py
            extracted: EmailData = parse_email_with_openai(body)

            results.append({
                "ID": email_id,
                "Name": extracted.name or "Не указано",
                "Phone": extracted.phone or "Отсутствует",
                "Subject": extracted.subject,
                "Urgency": extracted.urgency,
                "Error Flag": extracted.error_flag,
                "Reasoning": extracted.reasoning,
                "Edge Case Note": email.get("edge_case_note", ""),
                "Processing Status": "Успешно"
            })
        except Exception as e:
            logger.error(f"Сбой при обработке письма {email_id}: {str(e)}")
            results.append({
                "ID": email_id,
                "Name": "ОШИБКА",
                "Phone": "ОШИБКА",
                "Subject": email.get("subject", "Н/Д"),
                "Urgency": "High",
                "Error Flag": True,
                "Reasoning": f"Ошибка во время обработки: {str(e)}",
                "Edge Case Note": email.get("edge_case_note", ""),
                "Processing Status": "Сбой API"
            })

    # 3. Экспорт валидированных результатов в Excel
    logger.info(f"Сохранение результатов в файл: {OUTPUT_FILE}")
    df = pd.DataFrame(results)
    df.to_excel(OUTPUT_FILE, index=False, engine="openpyxl")
    logger.info("=== ПАЙПЛАЙН УСПЕШНО ЗАВЕРШИЛ РАБОТУ ===")


if __name__ == "__main__":
    run_automation()