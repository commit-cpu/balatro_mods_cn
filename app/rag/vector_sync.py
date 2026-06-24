from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.db.connection import connect
from app.rag.qdrant_store import build_tm_point


@dataclass(frozen=True)
class VectorSyncResult:
    synced_count: int
    failed_count: int


def sync_vector_outbox(db_path: Path, embedder, store, batch_size: int) -> VectorSyncResult:
    synced = 0
    failed = 0

    with connect(db_path) as db:
        rows = db.execute(
            """
            select
                vector_outbox.id as outbox_id,
                vector_outbox.collection,
                tm_entries.id as tm_entry_id,
                tm_entries.mod_id,
                tm_entries.unit_key,
                tm_entries.context_type,
                tm_entries.normalized_source,
                tm_entries.token_signature,
                tm_entries.quality,
                tm_entries.qdrant_point_id
            from vector_outbox
            join tm_entries on tm_entries.id = vector_outbox.tm_entry_id
            where vector_outbox.status = 'pending'
            order by vector_outbox.id
            limit ?
            """,
            (batch_size,),
        ).fetchall()

        if not rows:
            return VectorSyncResult(synced_count=0, failed_count=0)

        outbox_ids = [row["outbox_id"] for row in rows]
        db.executemany(
            "update vector_outbox set status = 'processing', updated_at = current_timestamp where id = ?",
            [(outbox_id,) for outbox_id in outbox_ids],
        )
        db.commit()

        try:
            vectors = embedder.embed_texts([row["normalized_source"] for row in rows])
            points = [
                build_tm_point(
                    point_id=row["qdrant_point_id"],
                    vector=vector,
                    tm_entry_id=row["tm_entry_id"],
                    mod_id=row["mod_id"],
                    unit_key=row["unit_key"],
                    context_type=row["context_type"],
                    token_signature=row["token_signature"],
                    quality=row["quality"],
                )
                for row, vector in zip(rows, vectors, strict=True)
            ]
            store.upsert_points(points)
        except Exception as exc:
            message = str(exc)
            db.executemany(
                """
                update vector_outbox
                set status = 'failed',
                    attempts = attempts + 1,
                    last_error = ?,
                    updated_at = current_timestamp
                where id = ?
                """,
                [(message, outbox_id) for outbox_id in outbox_ids],
            )
            db.commit()
            return VectorSyncResult(synced_count=0, failed_count=len(outbox_ids))

        db.executemany(
            """
            update vector_outbox
            set status = 'done',
                updated_at = current_timestamp
            where id = ?
            """,
            [(outbox_id,) for outbox_id in outbox_ids],
        )
        db.commit()
        synced = len(outbox_ids)

    return VectorSyncResult(synced_count=synced, failed_count=failed)
