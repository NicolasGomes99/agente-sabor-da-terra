from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from ...config import to_pernambuco_date


def _normalize_iso_date_str(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    parsed = to_pernambuco_date(value)
    return parsed.isoformat()


class TriageInput(BaseModel):
    message_text: str = Field(
        min_length=1,
        description="Texto original da mensagem recebida na triagem.",
    )
    received_at: datetime | date | str = Field(
        description="Data ou data/hora de recebimento da mensagem.",
    )
    sender: str | None = Field(
        default=None,
        description="Identificação do remetente no canal de origem.",
    )
    buyer_name: str | None = Field(
        default=None,
        description="Nome do comprador ou contato associado, quando conhecido.",
    )
    channel: str | None = Field(
        default=None,
        description="Canal de entrada (ex.: email, whatsapp, formulario_web).",
    )
    source_id: str | None = Field(
        default=None,
        description="Identificador externo da mensagem, quando disponível.",
    )
    conversation_history: str | None = Field(
        default=None,
        description=(
            "Histórico anterior da sessão de conversa enviado separadamente "
            "do texto da mensagem em análise."
        ),
    )

    @field_validator("message_text")
    @classmethod
    def _validate_message_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message_text must not be blank.")
        return stripped

    @field_validator("conversation_history")
    @classmethod
    def _normalize_conversation_history(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("received_at")
    @classmethod
    def _validate_received_at(
        cls,
        value: datetime | date | str,
    ) -> datetime | date | str:
        to_pernambuco_date(value)
        return value

    @property
    def received_date(self) -> date:
        return to_pernambuco_date(self.received_at)
