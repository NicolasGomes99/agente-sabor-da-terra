import asyncio
import hashlib
import itertools
import logging
import math
import re
import unicodedata
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol, runtime_checkable

from google import genai
from google.genai import types

from ..config import get_embedding_dimensions, get_embedding_model

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_/][a-z0-9]+)*")
_RETRY_DELAY_RE = re.compile(
    r"(?:retry\s+in\s+|'retryDelay'\s*:\s*')(\d+(?:\.\d+)?)s",
    re.IGNORECASE,
)
_DEFAULT_BATCH_SIZE = 50
_DEFAULT_MAX_RATE_LIMIT_RETRIES = 4
_MAX_RETRY_WAIT_SECONDS = 65.0


class EmbeddingGenerationError(RuntimeError):
    """Erro ao gerar embeddings para indexação ou consulta vetorial."""


def l2_normalize(vector: Sequence[float]) -> list[float]:
    values = [float(v) for v in vector]
    norm = math.sqrt(sum(v * v for v in values))
    if norm == 0.0:
        return values
    return [v / norm for v in values]


@runtime_checkable
class EmbeddingClient(Protocol):
    @property
    def model_name(self) -> str:
        ...

    @property
    def dimensions(self) -> int:
        ...

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        ...

    async def embed_query(self, text: str) -> list[float]:
        ...


def _is_rate_limit_error(error: Exception) -> bool:
    text = str(error)
    return "429" in text or "RESOURCE_EXHAUSTED" in text


def _extract_retry_delay_seconds(error: Exception, *, attempt: int) -> float:
    match = _RETRY_DELAY_RE.search(str(error))
    if match:
        parsed = float(match.group(1))
        return min(max(parsed + 1.0, 1.0), _MAX_RETRY_WAIT_SECONDS)
    return min(float(15 * (attempt + 1)), _MAX_RETRY_WAIT_SECONDS)


class GeminiEmbeddingClient:
    """Cliente de embeddings usando Google GenAI SDK com modelo e dimensão configuráveis."""

    def __init__(
        self,
        *,
        model: str | None = None,
        dimensions: int | None = None,
        batch_size: int = _DEFAULT_BATCH_SIZE,
        client: genai.Client | None = None,
        max_rate_limit_retries: int = _DEFAULT_MAX_RATE_LIMIT_RETRIES,
        sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._model = (model or get_embedding_model()).strip()
        if not self._model:
            raise ValueError("Embedding model must not be blank.")
        self._dimensions = (
            dimensions if dimensions is not None else get_embedding_dimensions()
        )
        if self._dimensions < 1:
            raise ValueError("Embedding dimensions must be positive.")
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1.")
        if max_rate_limit_retries < 0:
            raise ValueError("max_rate_limit_retries must be non-negative.")
        self._batch_size = batch_size
        self._client = client
        self._max_rate_limit_retries = max_rate_limit_retries
        self._sleep_fn = sleep_fn

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _get_client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client()
        return self._client

    def _embed_batch_sync(
        self,
        texts: list[str],
        *,
        task_type: str,
    ) -> list[list[float]]:
        client = self._get_client()
        response = client.models.embed_content(
            model=self._model,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=self._dimensions,
            ),
        )

        embeddings = getattr(response, "embeddings", None) or []
        if len(embeddings) != len(texts):
            raise EmbeddingGenerationError(
                f"O modelo '{self._model}' retornou {len(embeddings)} embeddings "
                f"para {len(texts)} textos."
            )

        vectors: list[list[float]] = []
        for item in embeddings:
            raw_values = getattr(item, "values", None)
            if not raw_values or len(raw_values) != self._dimensions:
                raise EmbeddingGenerationError(
                    f"Dimensão inesperada do embedding retornado por '{self._model}'."
                )
            vectors.append(l2_normalize(raw_values))
        return vectors

    async def _embed_batch_with_retry(
        self,
        texts: list[str],
        *,
        task_type: str,
    ) -> list[list[float]]:
        for attempt in range(self._max_rate_limit_retries + 1):
            try:
                return await asyncio.to_thread(
                    self._embed_batch_sync,
                    texts,
                    task_type=task_type,
                )
            except EmbeddingGenerationError:
                raise
            except Exception as error:
                if (
                    _is_rate_limit_error(error)
                    and attempt < self._max_rate_limit_retries
                ):
                    wait_seconds = _extract_retry_delay_seconds(
                        error,
                        attempt=attempt,
                    )
                    logger.info(
                        "Limite de taxa do modelo '%s' atingido; aguardando %.1fs "
                        "(tentativa %d/%d).",
                        self._model,
                        wait_seconds,
                        attempt + 1,
                        self._max_rate_limit_retries,
                    )
                    await self._sleep_fn(wait_seconds)
                    continue
                raise EmbeddingGenerationError(
                    f"Falha ao gerar embeddings com o modelo '{self._model}': {error}"
                ) from error
        raise EmbeddingGenerationError(
            f"Falha ao gerar embeddings com o modelo '{self._model}'."
        )

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        cleaned = [text.strip() for text in texts]
        if not cleaned:
            return []
        if any(not text for text in cleaned):
            raise ValueError("Document texts to embed must not be blank.")

        all_vectors: list[list[float]] = []
        for start in range(0, len(cleaned), self._batch_size):
            batch = cleaned[start : start + self._batch_size]
            batch_vectors = await self._embed_batch_with_retry(
                batch,
                task_type="RETRIEVAL_DOCUMENT",
            )
            all_vectors.extend(batch_vectors)
        return all_vectors

    async def embed_query(self, text: str) -> list[float]:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Query text to embed must not be blank.")
        vectors = await self._embed_batch_with_retry(
            [cleaned],
            task_type="RETRIEVAL_QUERY",
        )
        return vectors[0]


def _normalize_for_tokens(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return ascii_only.lower()


def _extract_hash_features(text: str) -> list[tuple[str, float]]:
    normalized = _normalize_for_tokens(text)
    tokens = _TOKEN_RE.findall(normalized)
    if not tokens:
        return []

    features: list[tuple[str, float]] = []
    for token in tokens:
        if len(token) == 1:
            continue
        features.append((f"tok:{token}", 1.0))
        # Também inclui subtokens de identificadores com hífen (ex.: lot-2026-0094)
        if "-" in token:
            features.append((f"id:{token}", 2.0))
            for part in token.split("-"):
                if len(part) >= 2:
                    features.append((f"part:{part}", 0.5))
        # Prefixos curtos ajudam flexões de português (certificacao/certificado, organica/organico)
        if len(token) >= 5 and token.isalpha():
            features.append((f"stem:{token[:5]}", 0.7))

    for left, right in itertools.pairwise(tokens):
        if len(left) >= 2 and len(right) >= 2:
            features.append((f"bi:{left}_{right}", 0.8))

    return features


class DeterministicHashEmbeddingClient:
    """Cliente determinístico offline para testes automatizados sem chamadas externas."""

    def __init__(
        self,
        *,
        dimensions: int = 128,
        model_name: str = "deterministic-hash-embedding",
    ) -> None:
        if dimensions < 8:
            raise ValueError("dimensions must be at least 8.")
        self._dimensions = dimensions
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_sync(self, text: str) -> list[float]:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Text to embed must not be blank.")
        vector = [0.0] * self._dimensions
        features = _extract_hash_features(cleaned)
        if not features:
            vector[0] = 1.0
            return vector
        for feature, weight in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            vector[bucket] += sign * weight
        normalized = l2_normalize(vector)
        if all(value == 0.0 for value in normalized):
            normalized[0] = 1.0
        return normalized

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_sync(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self.embed_sync(text)
