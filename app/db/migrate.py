from __future__ import annotations

import re
from pathlib import Path

from app.config import load_settings
from app.db.connection import connect


_MIGRATION_RE = re.compile(r"^(\d+)_(.+)\.sql$")


def migrate(
    db_path: Path | str | None = None,
    migrations_dir: Path | str = Path("migrations"),
) -> None:
    if db_path is None:
        db_path = load_settings().sqlite.database_path

    migrations = _load_migrations(Path(migrations_dir))
    with connect(db_path) as db:
        db.execute(
            """
            create table if not exists schema_migrations (
                version integer primary key,
                name text not null,
                applied_at text not null default current_timestamp
            )
            """
        )
        applied = {
            row["version"]
            for row in db.execute("select version from schema_migrations").fetchall()
        }

        for version, name, path in migrations:
            if version in applied:
                continue
            db.executescript(path.read_text(encoding="utf-8"))
            db.execute(
                "insert into schema_migrations(version, name) values (?, ?)",
                (version, name),
            )
        db.commit()


def _load_migrations(migrations_dir: Path) -> list[tuple[int, str, Path]]:
    if not migrations_dir.exists():
        raise FileNotFoundError(f"Migrations directory not found: {migrations_dir}")

    migrations: list[tuple[int, str, Path]] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _MIGRATION_RE.match(path.name)
        if match is None:
            continue
        migrations.append((int(match.group(1)), match.group(2), path))
    return migrations


if __name__ == "__main__":
    migrate()
