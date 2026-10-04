from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from pgvector.sqlalchemy import Vector


class _MigrationOperations:
    def __init__(self) -> None:
        self.dropped: list[tuple[str, str]] = []
        self.added: list[tuple[str, object]] = []

    def drop_column(self, table: str, name: str) -> None:
        self.dropped.append((table, name))

    def add_column(self, table: str, column: object) -> None:
        self.added.append((table, column))


def _load_migration() -> ModuleType:
    migration_path = (
        Path(__file__).parents[2] / "alembic" / "versions" / "0003_local_embedding_dimension.py"
    )
    spec = importlib.util.spec_from_file_location(
        "local_embedding_dimension_migration", migration_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("operation", "expected_dimension"), [("upgrade", 384), ("downgrade", 1536)]
)
def test_embedding_migration_replaces_vector_column(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    expected_dimension: int,
) -> None:
    migration = _load_migration()
    operations = _MigrationOperations()
    monkeypatch.setattr(migration, "op", operations)

    getattr(migration, operation)()

    assert operations.dropped == [("source_fragments", "embedding")]
    table, column = operations.added[0]
    assert table == "source_fragments"
    assert isinstance(column.type, Vector)
    assert column.type.dim == expected_dimension
