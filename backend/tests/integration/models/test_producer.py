from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Producer

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.mark.parametrize("active", [True, False])
async def test_producer_persists_with_generated_uuid(
    db_session: AsyncSession, active: bool,
) -> None:
    data = {
        "code": "P001", "name": "Ana Silva", "cpf": "01234567890", "active": active,
        "phone": "81999990000", "email": "ana@example.com", "address": "Rua das Flores, 10",
        "municipality": "Caruaru",
    }
    producer = Producer(**data)
    db_session.add(producer)
    await db_session.flush()
    producer_id = producer.id
    assert isinstance(producer_id, UUID)
    db_session.expunge_all()

    persisted = await db_session.get(Producer, producer_id)

    assert persisted is not None
    assert {field: getattr(persisted, field) for field in data} == data


async def test_producer_persists_with_explicit_uuid(db_session: AsyncSession) -> None:
    producer_id = uuid4()
    db_session.add(Producer(
        id=producer_id, code="P001", name="Ana Silva", cpf="01234567890", active=True,
    ))
    await db_session.flush()
    db_session.expunge_all()

    persisted = await db_session.get(Producer, producer_id)

    assert persisted is not None
    assert persisted.id == producer_id
    assert persisted.code == "P001"


async def test_producer_allows_missing_optional_fields(db_session: AsyncSession) -> None:
    producer = Producer(code="P001", name="Ana Silva", cpf="01234567890", active=True)
    db_session.add(producer)
    await db_session.flush()
    producer_id = producer.id
    db_session.expunge_all()

    persisted = await db_session.get(Producer, producer_id)

    assert persisted is not None
    assert persisted.phone is None
    assert persisted.email is None
    assert persisted.address is None
    assert persisted.municipality is None


@pytest.mark.parametrize("field", ["code", "name", "cpf", "active"])
async def test_producer_requires_mandatory_fields(
    db_session: AsyncSession, field: str,
) -> None:
    data = {"code": "P001", "name": "Ana Silva", "cpf": "01234567890", "active": True}
    data[field] = None
    db_session.add(Producer(**data))

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.parametrize("field", ["code", "name", "cpf"])
@pytest.mark.parametrize("value", ["", "   ", "\t", "\n", " \t\r\n "])
async def test_producer_rejects_blank_identity_fields(
    db_session: AsyncSession, field: str, value: str,
) -> None:
    data = {"code": "P001", "name": "Ana Silva", "cpf": "01234567890", "active": True}
    data[field] = value
    db_session.add(Producer(**data))

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.parametrize("field", ["code", "cpf"])
async def test_producer_rejects_duplicate_unique_fields(
    db_session: AsyncSession, field: str,
) -> None:
    first = {"code": "P001", "name": "Ana Silva", "cpf": "01234567890", "active": True}
    db_session.add(Producer(**first))
    await db_session.flush()
    second = {"code": "P002", "name": "João Silva", "cpf": "12345678901", "active": False}
    second[field] = first[field]
    db_session.add(Producer(**second))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_producers_can_share_name(db_session: AsyncSession) -> None:
    first = Producer(code="P001", name="Ana Silva", cpf="01234567890", active=True)
    second = Producer(code="P002", name="Ana Silva", cpf="12345678901", active=False)
    db_session.add_all([first, second])
    await db_session.flush()
    first_id, second_id = first.id, second.id
    assert first_id != second_id
    db_session.expunge_all()

    persisted_first = await db_session.get(Producer, first_id)
    persisted_second = await db_session.get(Producer, second_id)

    assert persisted_first is not None
    assert persisted_second is not None
    assert persisted_first.name == persisted_second.name == "Ana Silva"
