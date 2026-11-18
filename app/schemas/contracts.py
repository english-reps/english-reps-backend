import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=254)
    password: SecretStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def password_length(cls, value: SecretStr) -> SecretStr:
        if not 12 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Password must contain 12 to 128 characters")
        return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str


class AuthOut(BaseModel):
    user: UserOut
    csrf_token: str


class ProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    entry_id: str
    category: Literal["vocabulary", "listening"]
    status: Literal["mastered", "review", "unseen"]
    attempts: int
    correct: int
    updated_at: datetime


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: uuid.UUID
    entry_id: str = Field(max_length=32)
    kind: Literal["card", "quiz", "listening"]
    rating: Literal["mastered", "review", "unseen"] | None = None
    answer: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def check_answer(self) -> Self:
        if self.kind == "card":
            if self.rating is None or self.answer is not None:
                raise ValueError("Cards require rating only")
        elif self.answer is None or self.rating is not None:
            raise ValueError("Quizzes require answer only")
        return self
