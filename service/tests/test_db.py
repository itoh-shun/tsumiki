import stat
import sqlite3

import pytest

from app.db import SCHEMA_VERSION, connect, init_db


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "tsumiki.db"
    c = connect(db_path)
    init_db(c)
    yield c
    c.close()


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {row["name"] for row in rows}


def test_init_db_creates_tables(conn):
    names = _table_names(conn)
    assert "projects" in names
    assert "tasks" in names


def test_journal_mode_is_wal(conn):
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_init_db_is_idempotent(conn):
    # 2回目の呼び出しでも例外にならない
    init_db(conn)
    init_db(conn)


def test_user_version_is_set(conn):
    # B7: 将来のマイグレーションのためのスキーマバージョン管理
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == SCHEMA_VERSION
    assert version > 0


def test_db_directory_and_file_permissions_are_restricted(tmp_path):
    # B1: ディレクトリ 0700・DB ファイル 0600。既存ディレクトリでも chmod されること
    db_dir = tmp_path / "nested"
    db_dir.mkdir(mode=0o755)  # あえて緩いパーミッションで事前に作っておく
    db_path = db_dir / "tsumiki.db"

    c = connect(db_path)
    try:
        dir_mode = stat.S_IMODE(db_dir.stat().st_mode)
        file_mode = stat.S_IMODE(db_path.stat().st_mode)
        assert dir_mode == 0o700
        assert file_mode == 0o600
    finally:
        c.close()


def test_invalid_state_raises_integrity_error(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO tasks (title, state, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            ("test task", "not-a-valid-state", "2026-09-01T00:00:00Z", "2026-09-01T00:00:00Z"),
        )
