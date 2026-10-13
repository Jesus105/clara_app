from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class Login(BaseModel):
    password: str = Field(max_length=200)


class TextInput(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=3, max_length=200)
    contact: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=300)
    country: str = Field(default="México", max_length=60)
    kind: Literal["news", "hiring", "email", "text"] = "news"
    content: str = Field(min_length=20, max_length=12000)


class DraftEdit(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=10, max_length=6000)
    revision: int = Field(ge=1)


class Approval(BaseModel):
    revision: int = Field(ge=1)


class Rules(BaseModel):
    finance_hiring: int = Field(default=40, ge=0, le=60)
    funding: int = Field(default=30, ge=0, le=60)
    expansion: int = Field(default=20, ge=0, le=60)
    corporate_domain: int = Field(default=10, ge=0, le=20)
    dm_threshold: int = Field(default=80, ge=1, le=100)
    template: str = Field(default="Presenta cómo Clara ayuda a centralizar tarjetas corporativas y controlar gastos. Usa la señal observada, evita promesas o cifras no verificadas y cierra con una invitación a una conversación de 15 minutos.", min_length=20, max_length=1500)


class ExtractedSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["finance_hiring", "funding", "expansion"]
    source_id: str
    evidence: str = Field(min_length=10, max_length=1000)


class Analysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=10, max_length=1500)
    angle: str = Field(min_length=10, max_length=1500)
    signals: list[ExtractedSignal] = Field(max_length=6)
    subject: str = Field(min_length=5, max_length=200)
    body: str = Field(min_length=20, max_length=4000)

