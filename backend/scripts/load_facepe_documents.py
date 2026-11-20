import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.database import get_session_maker
from api.dependencies import get_document_storage, get_embedding_client
from api.rag.indexing import DocumentIndexingService
from api.repositories.document import DocumentRepository

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


async def run(
    data_dir: Path,
    *,
    reindex_existing: bool = False,
    retry_failed_only: bool = False,
) -> None:
    storage = get_document_storage()
    embedding_client = get_embedding_client()
    session_maker = get_session_maker()

    async with session_maker() as session:
        service = DocumentIndexingService(
            DocumentRepository(session),
            storage,
            embedding_client,
        )
        if retry_failed_only:
            summaries = await service.retry_pending_and_failed()
            print(
                f"Reprocessamento concluído ({len(summaries)} documentos avaliados, "
                f"modelo={embedding_client.model_name}, dim={embedding_client.dimensions}):"
            )
            for item in summaries:
                print(
                    f"  - {item.original_filename}: status={item.status} "
                    f"(trechos={item.active_chunk_count})"
                )
            return

        summary = await service.load_facepe_documents(
            data_dir,
            reindex_existing=reindex_existing,
        )

    print(
        f"Carga documental Facepe concluída "
        f"(modelo={embedding_client.model_name}, dim={embedding_client.dimensions}):"
    )
    print(f"  documentos criados:      {summary.documents_created}")
    print(f"  documentos reutilizados: {summary.documents_reused}")
    print(f"  documentos indexados:    {summary.documents_indexed}")
    print(f"  documentos ignorados:    {summary.documents_skipped}")
    print(f"  total de trechos ativos: {summary.total_active_chunks}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Armazena, processa e indexa os 20 documentos textuais e os 5 CSVs "
            "da base documental da Facepe no PostgreSQL com pgvector."
        ),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Diretório raiz da base Facepe (padrão: backend/data).",
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Reindexa documentos já cadastrados preservando IDs e citações existentes.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Reprocessa apenas documentos atualmente pendentes ou com falha.",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            args.data_dir,
            reindex_existing=args.reindex,
            retry_failed_only=args.retry_failed,
        )
    )


if __name__ == "__main__":
    main()
