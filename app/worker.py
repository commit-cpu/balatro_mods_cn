from __future__ import annotations

from app.config import load_settings


def main() -> None:
    settings = load_settings()
    print(
        f"{settings.worker.name} ready: sqlite={settings.sqlite.database_path} "
        f"qdrant={settings.qdrant.url} repos={settings.git.repos_dir}"
    )


if __name__ == "__main__":
    main()
