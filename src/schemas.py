import re
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class SubjectCategory(str, Enum):
    TECH_SUPPORT = "Technical Support"
    BILLING_SALES = "Billing & Sales"
    PARTNERSHIP = "Partnership"
    GENERAL = "General Inquiry"
    SPAM = "Spam/Irrelevant"


class UrgencyLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class EmailExtractionSchema(BaseModel):
    """Pydantic-схема, передаваемая в OpenAI API для Structured Outputs."""
    full_name: Optional[str] = Field(
        default=None,
        description="Имя и фамилия автора письма. Если имя не указано явно — null."
    )
    phone_number: Optional[str] = Field(
        default=None,
        description="Номер телефона автора в международном формате E.164 (например, +79991234567). Если отсутствует — null."
    )
    subject_category: SubjectCategory = Field(
        description="Категория обращения на основе контекста."
    )
    urgency_level: UrgencyLevel = Field(
        description="Срочность обработки запроса."
    )
    summary: str = Field(
        description="Краткая суть обращения (1-2 предложения)."
    )

    @field_validator("phone_number")
    @classmethod
    def validate_and_clean_phone(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        # Очистка от скобок, тире, пробелов
        cleaned = re.sub(r"[^\d+]", "", v)
        # Проверка формата E.164 (+ и от 10 до 15 цифр)
        if re.match(r"^\+?[1-9]\d{9,14}$", cleaned):
            return cleaned if cleaned.startswith("+") else f"+{cleaned}"
        return None  # Помечаем как невалидный для ручного разбора

    @field_validator("full_name")
    @classmethod
    def normalize_name(cls, v: Optional[str]) -> str:
        if not v or v.strip().lower() in ["unknown", "н/д", "не указано", "none"]:
            return "Не указано"
        return v.strip().title()