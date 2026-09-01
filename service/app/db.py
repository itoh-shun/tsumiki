"""SQLite 接続とスキーマ定義。"""

import os
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT,
    state TEXT NOT NULL CHECK (state IN ('inbox', 'next', 'waiting', 'someday', 'done')),
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    context TEXT,
    due TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due);
"""

# スキーマのバージョン。今はまだマイグレーションを持たないが、既存 DB がまだ
# 存在しないこのタイミングでのみ、コスト無しで入れておける(B7)。
SCHEMA_VERSION = 1


def connect(db_path: str | Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """DB へ接続する。ディレクトリが無ければ作成し、WAL と外部キー制約を有効化する。

    `check_same_thread=False` は、Starlette の TestClient のように ASGI アプリを
    別スレッドで(逐次・非並行に)呼び出すテストでのみ使う想定。通常の実行経路では
    既定の True のままにし、単一接続をアプリ全体で共有する前提を壊さない。
    """
    if str(db_path) == ":memory:":
        target = ":memory:"
        path = None
    else:
        path = Path(db_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        # mkdir(exist_ok=True) は既存ディレクトリの mode を変えないので明示的に chmod する(B1)
        os.chmod(path.parent, 0o700)
        target = str(path)
    conn = sqlite3.connect(target, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    if path is not None:
        # DB ファイル本体は sqlite3.connect() が umask 込みで作る(既定 0644)ので
        # 明示的に 0600 へ絞る。WAL モードの副産物(-wal/-shm)も同様に絞る。
        os.chmod(path, 0o600)
        for suffix in ("-wal", "-shm"):
            side_file = path.parent / (path.name + suffix)
            if side_file.exists():
                os.chmod(side_file, 0o600)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """スキーマを作成する。冪等（何度呼んでもエラーにならない）。"""
    conn.executescript(SCHEMA)
    # PRAGMA はバインドパラメータを受け付けないため、リテラルとして埋め込む。
    # SCHEMA_VERSION はモジュール内の定数で、外部入力は混じらない。
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
