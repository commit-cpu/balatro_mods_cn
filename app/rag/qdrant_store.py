from __future__ import annotations

from collections.abc import Mapping

from qdrant_client import QdrantClient, models


PAYLOAD_INDEXES: dict[str, models.PayloadSchemaType] = {
    "tm_entry_id": models.PayloadSchemaType.INTEGER,
    "mod_id": models.PayloadSchemaType.KEYWORD,
    "context_type": models.PayloadSchemaType.KEYWORD,
    "token_signature": models.PayloadSchemaType.KEYWORD,
    "quality": models.PayloadSchemaType.KEYWORD,
}


def build_tm_point(
    *,
    point_id: str,
    vector: list[float],
    tm_entry_id: int,
    mod_id: str,
    unit_key: str,
    context_type: str,
    token_signature: str,
    quality: str,
) -> models.PointStruct:
    return models.PointStruct(
        id=point_id,
        vector=vector,
        payload={
            "tm_entry_id": tm_entry_id,
            "mod_id": mod_id,
            "unit_key": unit_key,
            "context_type": context_type,
            "token_signature": token_signature,
            "quality": quality,
        },
    )


def build_payload_filter(filters: Mapping[str, str] | None) -> models.Filter | None:
    if not filters:
        return None
    return models.Filter(
        must=[
            models.FieldCondition(key=key, match=models.MatchValue(value=value))
            for key, value in filters.items()
        ]
    )


class QdrantTmStore:
    def __init__(
        self,
        *,
        url: str,
        api_key: str | None,
        collection: str,
        client: QdrantClient | None = None,
        timeout: int = 30,
    ) -> None:
        self.collection = collection
        self._client = client or QdrantClient(url=url, api_key=api_key, timeout=timeout)

    def ensure_collection(self, vector_size: int) -> None:
        if not self._client.collection_exists(collection_name=self.collection):
            self._client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )

        for field_name, schema in PAYLOAD_INDEXES.items():
            try:
                self._client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field_name,
                    field_schema=schema,
                )
            except Exception as exc:
                if "already exists" not in str(exc).lower():
                    raise

    def upsert_points(self, points: list[models.PointStruct]) -> None:
        if not points:
            return
        self._client.upsert(collection_name=self.collection, points=points)

    def collection_info(self):
        return self._client.get_collection(collection_name=self.collection)

    def search(
        self,
        vector: list[float],
        top_k: int,
        filters: Mapping[str, str] | None = None,
    ) -> list[models.ScoredPoint]:
        response = self._client.query_points(
            collection_name=self.collection,
            query=vector,
            query_filter=build_payload_filter(filters),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        return list(response.points)
