from __future__ import annotations

import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from app.config import load_settings
from app.db.migrate import migrate as run_migrations
from app.rag.ollama_embeddings import OllamaEmbeddingClient
from app.rag.qdrant_store import QdrantTmStore
from app.rag.retriever import retrieve_references
from app.rag.tm_importer import import_locale_pair
from app.rag.vector_sync import sync_vector_outbox


app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def migrate() -> None:
    settings = load_settings()
    run_migrations(settings.sqlite.database_path)
    console.print(f"Migrations applied: {settings.sqlite.database_path}")


@app.command("import-local-tm")
def import_local_tm(
    repo: Path = typer.Option(..., exists=True, file_okay=False),
    mod_id: str = typer.Option(...),
    source: str = typer.Option("localization/en-us.lua"),
    target: str = typer.Option("localization/zh_CN.lua"),
) -> None:
    settings = load_settings()
    result = import_locale_pair(
        db_path=Path(settings.sqlite.database_path),
        mod_id=mod_id,
        repo_path=repo,
        source_locale_path=source,
        target_locale_path=target,
        collection=settings.qdrant.collection,
    )
    console.print(
        f"Imported {result.imported_pair_count} TM entries for {result.mod_id}; "
        f"skipped {result.skipped_count}."
    )


@app.command("sync-vectors")
def sync_vectors(limit: int = typer.Option(100, min=1)) -> None:
    settings = load_settings()
    embedder = OllamaEmbeddingClient(
        base_url=settings.embedding.base_url,
        model=settings.embedding.model,
    )
    store = _qdrant_store()
    store.ensure_collection(embedder.embedding_dimension())
    result = sync_vector_outbox(
        db_path=Path(settings.sqlite.database_path),
        embedder=embedder,
        store=store,
        batch_size=limit,
    )
    console.print(f"Synced {result.synced_count} vectors; failed {result.failed_count}.")


@app.command("qdrant-status")
def qdrant_status() -> None:
    settings = load_settings()
    store = _qdrant_store()
    info = store.collection_info()
    console.print(f"Collection: {settings.qdrant.collection}")
    console.print(info)


@app.command()
def search(query: str, top_k: int = typer.Option(5, min=1)) -> None:
    settings = load_settings()
    embedder = OllamaEmbeddingClient(
        base_url=settings.embedding.base_url,
        model=settings.embedding.model,
    )
    store = _qdrant_store()
    result = retrieve_references(
        db_path=Path(settings.sqlite.database_path),
        query_text=query,
        embedder=embedder,
        store=store,
        top_k=top_k,
    )
    table = Table("score", "mod", "unit_key", "source", "target")
    for ref in result.references:
        table.add_row(
            f"{ref.score:.4f}",
            ref.mod_id,
            ref.unit_key,
            ref.source_text,
            ref.target_text,
        )
    console.print(table)


def _qdrant_store() -> QdrantTmStore:
    load_dotenv()
    settings = load_settings()
    return QdrantTmStore(
        url=settings.qdrant.url,
        api_key=os.environ.get("QDRANT_API_KEY"),
        collection=settings.qdrant.collection,
        timeout=settings.qdrant.timeout_seconds,
    )


if __name__ == "__main__":
    app()
