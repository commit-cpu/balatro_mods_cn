from pathlib import Path

from app.db.connection import connect
from app.db.migrate import migrate
from app.rag.retriever import retrieve_references


class FakeEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0]]


class FakeHit:
    def __init__(self, tm_entry_id: int, score: float) -> None:
        self.payload = {"tm_entry_id": tm_entry_id}
        self.score = score


class FakeStore:
    def search(self, vector, top_k, filters=None):
        return [FakeHit(1, 0.93)]


def test_retrieve_references_hydrates_qdrant_hits_from_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    migrate(db_path)
    with connect(db_path) as db:
        db.execute(
            """
            insert into tm_entries(
                id, mod_id, unit_key, context_type, source_text, target_text,
                normalized_source, token_signature, quality, qdrant_point_id,
                source_hash, target_hash
            ) values (
                1, 'mod', 'k', 'joker_description_line', 'Gain +#1# Mult',
                '获得 +#1# 倍率', 'gain +<var_1> mult', 'var_1',
                'imported_human', 'p1', 's', 't'
            )
            """
        )
        db.commit()

    result = retrieve_references(
        db_path=db_path,
        query_text="Gain more Mult",
        embedder=FakeEmbedder(),
        store=FakeStore(),
        top_k=8,
    )

    assert result.references[0].target_text == "获得 +#1# 倍率"
    assert result.references[0].score == 0.93
    assert result.trace.result_count == 1
    assert result.trace.hit_ids == [1]
    with connect(db_path) as db:
        trace_count = db.execute("select count(*) as c from rag_traces").fetchone()["c"]
    assert trace_count == 1
