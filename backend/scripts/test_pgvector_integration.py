"""Standalone pgvector integration check against a real PostgreSQL instance.

The pytest suite runs on SQLite (no vector extension), so it can only prove
the JSON fallback path in ``app/models/types.py`` works. This script instead
verifies the PostgreSQL-only path end to end: the ``vector`` extension
installs, ``documents.embedding`` is a native ``vector`` column, and the
``<=>`` distance operator ranks results the way ``DocumentRepository.
semantic_search`` and ``SearchService._semantic`` rely on.

Not run by pytest / CI. Run manually against the docker-compose Postgres:

    docker compose up -d db
    cd backend && alembic upgrade head
    .venv/Scripts/python.exe scripts/test_pgvector_integration.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

DIM = settings.embedding_dim


def _vec(values: list[float]) -> str:
    """Render a Python list as a pgvector text literal, e.g. ``[1,0,0]``."""
    return "[" + ",".join(str(v) for v in values) + "]"


async def _check_extension(conn) -> None:
    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    version = (
        await conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
    ).scalar_one_or_none()
    if version is None:
        raise AssertionError("vector extension did not install")
    print(f"[ok] vector extension installed (version {version})")


async def _check_column_type(conn) -> None:
    col_type = (
        await conn.execute(
            text(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = 'documents'::regclass AND attname = 'embedding'"
            )
        )
    ).scalar_one_or_none()
    if col_type is None:
        raise AssertionError("documents.embedding column not found — run `alembic upgrade head`")
    if not col_type.startswith("vector"):
        raise AssertionError(
            f"documents.embedding is {col_type!r}, expected a native vector(...) column "
            "— run `alembic upgrade head` to apply 0008_pgvector_embeddings"
        )
    print(f"[ok] documents.embedding column type = {col_type}")


async def _check_distance_operator(conn) -> None:
    """The <=> operator must rank an identical vector closer than an orthogonal one."""
    query = [1.0, 0.0] + [0.0] * (DIM - 2)
    near = [1.0, 0.0] + [0.0] * (DIM - 2)  # cosine distance 0 from query
    far = [0.0, 1.0] + [0.0] * (DIM - 2)  # cosine distance 1 from query

    rows = (
        await conn.execute(
            text(
                "SELECT label, embedding <=> CAST(:query AS vector) AS distance FROM ("
                "  SELECT 'near' AS label, CAST(:near AS vector) AS embedding "
                "  UNION ALL SELECT 'far', CAST(:far AS vector)"
                ") AS candidates "
                "ORDER BY distance"
            ),
            {"query": _vec(query), "near": _vec(near), "far": _vec(far)},
        )
    ).all()

    labels = [row.label for row in rows]
    if labels != ["near", "far"]:
        raise AssertionError(f"<=> operator did not rank as expected: {rows!r}")
    print(f"[ok] <=> operator ranks nearest neighbor first: {rows[0].label} (distance={rows[0].distance})")


async def main() -> int:
    uri = settings.sqlalchemy_database_uri
    if not uri.startswith("postgresql"):
        print(f"Configured database is not PostgreSQL ({uri!r}).")
        print("Set DATABASE_URL, or POSTGRES_HOST/PORT/USER/PASSWORD/DB, to the docker-compose db.")
        return 1

    engine = create_async_engine(uri, echo=False, future=True, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await _check_extension(conn)
            await _check_column_type(conn)
            await _check_distance_operator(conn)
    except Exception as exc:  # connection refused, auth failure, missing table, etc.
        print(f"pgvector integration check FAILED: {exc}")
        print(
            f"Is the docker-compose db up? Try: docker compose up -d db "
            f"(expects {settings.postgres_host}:{settings.postgres_port})"
        )
        return 1
    finally:
        await engine.dispose()

    print("pgvector integration check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
