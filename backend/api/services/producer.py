from uuid import UUID

from ..models.producer import Producer
from ..models.product import Product
from ..repositories.producer import ProducerRepository
from ..schemas.producer import ProducerResponse
from ..schemas.product import ProductResponse


class ProducerNotFoundError(LookupError):
    pass


def _build_response(producer: Producer, products: list[Product]) -> ProducerResponse:
    return ProducerResponse(
        id=producer.id,
        code=producer.code,
        name=producer.name,
        cpf=producer.cpf,
        active=producer.active,
        phone=producer.phone,
        email=producer.email,
        address=producer.address,
        municipality=producer.municipality,
        products=[ProductResponse.model_validate(product) for product in products],
    )


class ProducerService:
    def __init__(self, repository: ProducerRepository) -> None:
        self.repository = repository

    async def list_producers(self, product_id: UUID | None = None) -> list[ProducerResponse]:
        producers = await self.repository.list_all(product_id=product_id)
        if not producers:
            return []

        products_by_producer = await self.repository.list_products_by_producer_ids(
            [producer.id for producer in producers]
        )
        return [
            _build_response(producer, products_by_producer[producer.id])
            for producer in producers
        ]

    async def get_producer(self, producer_id: UUID) -> ProducerResponse:
        producer = await self.repository.get_by_id(producer_id)
        if producer is None:
            raise ProducerNotFoundError(producer_id)

        products_by_producer = await self.repository.list_products_by_producer_ids([producer.id])
        return _build_response(producer, products_by_producer[producer.id])
