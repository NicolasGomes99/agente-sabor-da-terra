from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Producer(Base):
    __tablename__ = "producers"
    __table_args__ = (
        CheckConstraint("code ~ '[^[:space:]]'", name="ck_producers_code_not_blank"),
        CheckConstraint("name ~ '[^[:space:]]'", name="ck_producers_name_not_blank"),
        CheckConstraint("cpf ~ '[^[:space:]]'", name="ck_producers_cpf_not_blank"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    cpf: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    municipality: Mapped[str | None] = mapped_column(String, nullable=True)
