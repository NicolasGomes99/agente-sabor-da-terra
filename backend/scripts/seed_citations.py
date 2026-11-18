import asyncio
from io import BytesIO
from uuid import uuid4

from sqlalchemy import select

from api.database import get_session_maker
from api.dependencies import get_document_storage
from api.models.chat_message import ChatMessage
from api.models.chat_session import ChatSession
from api.models.citation import Citation
from api.models.document import Document, DocumentChunk
from api.models.user import User


async def seed_citation_scenario() -> None:
    storage = get_document_storage()
    session_maker = get_session_maker()

    async with session_maker() as session:
        user = await session.scalar(select(User).limit(1))
        if user is None:
            raise RuntimeError(
                "Nenhum usuário encontrado no banco. Cadastre ou faça login com um usuário antes de rodar o seed."
            )

        storage_key = f"seed-{uuid4().hex}"
        sample_content = (
            b"Politica Comercial Sabor da Terra - Safra 2026\n\n"
            b"Clausula 4.2: Pedidos confirmados ate as 14h tem prazo maximo de entrega "
            b"de 48 horas uteis na regiao metropolitana, com lote minimo de 150 kg."
        )
        storage.save(storage_key, BytesIO(sample_content))

        document = Document(
            original_filename="politica-comercial-2026.txt",
            storage_key=storage_key,
        )
        session.add(document)
        await session.flush()

        chunk = DocumentChunk(
            document_id=document.id,
            content=(
                "Cláusula 4.2: Pedidos confirmados até as 14h têm prazo máximo de entrega "
                "de 48 horas úteis na região metropolitana, com lote mínimo de 150 kg."
            ),
            embedding=None,
        )
        session.add(chunk)
        await session.flush()

        chat_session = ChatSession(
            user_id=user.id,
            title="Validação de fontes - Política Comercial",
        )
        session.add(chat_session)
        await session.flush()

        user_message = ChatMessage(
            session_id=chat_session.id,
            role="user",
            content="Qual é o prazo de entrega e o lote mínimo para pedidos até 14h?",
        )
        assistant_message = ChatMessage(
            session_id=chat_session.id,
            role="assistant",
            content=(
                "De acordo com a política comercial vigente, pedidos confirmados até as 14h "
                "têm prazo máximo de entrega de 48 horas úteis na região metropolitana, "
                "respeitando o lote mínimo de 150 kg."
            ),
        )
        session.add_all([user_message, assistant_message])
        await session.flush()

        citation = Citation(
            message_id=assistant_message.id,
            chunk_id=chunk.id,
        )
        session.add(citation)
        await session.commit()

        print("Cenário de teste criado com sucesso:")
        print(f"  user_email:   {user.email}")
        print(f"  session_id:   {chat_session.id}")
        print(f"  message_id:   {assistant_message.id}")
        print(f"  document_id:  {document.id} ({document.original_filename})")
        print(f"  chunk_id:     {chunk.id}")


if __name__ == "__main__":
    asyncio.run(seed_citation_scenario())