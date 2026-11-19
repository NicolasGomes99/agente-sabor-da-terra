import csv
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.load import import_facepe
from api.models import Lot, LotImport, Order, OrderItem, Producer, Product

pytestmark = pytest.mark.asyncio

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def facepe_files() -> tuple[Path, Path]:
    producers = DATA_DIR / "produtores.csv"
    lots = DATA_DIR / "lotes.csv"
    if not producers.exists() or not lots.exists():
        pytest.skip("Arquivos da base Facepe ausentes.")
    return producers, lots


async def _count(session: AsyncSession, model) -> int:
    return await session.scalar(select(func.count()).select_from(model))


async def _lot_by_record(session: AsyncSession, record_id: str) -> Lot:
    imp = await session.scalar(
        select(LotImport).where(LotImport.record_id == record_id)
    )
    assert imp is not None
    lot = await session.get(Lot, imp.lot_id)
    assert lot is not None
    return lot


async def test_imports_catalog_producers_links_and_lots(
    db_session: AsyncSession,
    facepe_files: tuple[Path, Path],
) -> None:
    producers_rows = _read(facepe_files[0])
    lots_rows = _read(facepe_files[1])

    summary = await import_facepe(db_session, producers_rows, lots_rows)

    assert summary.producers_created == 18
    assert summary.products_created > 0
    assert summary.links_created > 0
    assert summary.lots_created == 20
    assert summary.lots_reused == 0

    assert await _count(db_session, Producer) == 18
    assert await _count(db_session, Product) > 0
    assert await _count(db_session, Lot) == 20
    assert await _count(db_session, Order) == 0
    assert await _count(db_session, OrderItem) == 0

    active = await db_session.scalar(
        select(Producer.active).where(Producer.code == "P004")
    )
    inactive = await db_session.scalar(
        select(Producer.active).where(Producer.code == "P015")
    )
    assert active is True
    assert inactive is False


async def test_imported_lots_have_null_item_and_expected_dates_and_units(
    db_session: AsyncSession,
    facepe_files: tuple[Path, Path],
) -> None:
    await import_facepe(db_session, _read(facepe_files[0]), _read(facepe_files[1]))

    lots = list(await db_session.scalars(select(Lot)))
    assert all(lot.item_id is None for lot in lots)
    assert all(lot.availability_confirmed is None for lot in lots)

    alface = await _lot_by_record(db_session, "LOT-2026-0094")
    assert alface.quantity == Decimal(300)
    assert alface.unit == "unidades"
    assert alface.delivery_date.isoformat() == "2026-09-08"

    coentro = await _lot_by_record(db_session, "LOT-2026-0095")
    assert coentro.quantity == Decimal(150)
    assert coentro.unit == "maços"
    assert coentro.delivery_date.isoformat() == "2026-09-08"

    couve = await _lot_by_record(db_session, "LOT-2026-0099")
    assert couve.quantity == Decimal(40)
    assert couve.unit is None


async def test_import_control_recovers_original_line(
    db_session: AsyncSession,
    facepe_files: tuple[Path, Path],
) -> None:
    await import_facepe(db_session, _read(facepe_files[0]), _read(facepe_files[1]))

    imp = await db_session.scalar(
        select(LotImport).where(LotImport.record_id == "LOT-2026-0094")
    )
    assert imp is not None
    assert imp.source_file == "lotes.csv"
    assert isinstance(imp.lot_id, UUID)
    assert imp.record_fields["produto"] == "alface"
    assert imp.record_fields["pedido_id"] == "PED-2026-SEP-008"
    assert imp.record_fields["produtor_id"] == "P004"


async def test_reimport_preserves_uuids_and_has_no_duplicates(
    db_session: AsyncSession,
    facepe_files: tuple[Path, Path],
) -> None:
    producers_rows = _read(facepe_files[0])
    lots_rows = _read(facepe_files[1])

    await import_facepe(db_session, producers_rows, lots_rows)
    first_ids = {
        imp.record_id: imp.lot_id
        for imp in await db_session.scalars(select(LotImport))
    }

    summary = await import_facepe(db_session, producers_rows, lots_rows)

    assert summary.lots_created == 0
    assert summary.lots_reused == 20
    assert summary.producers_created == 0
    assert summary.products_created == 0

    second_ids = {
        imp.record_id: imp.lot_id
        for imp in await db_session.scalars(select(LotImport))
    }
    assert second_ids == first_ids
    assert await _count(db_session, Lot) == 20
