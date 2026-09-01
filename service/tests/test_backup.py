import stat
import sqlite3
from datetime import date

import pytest

from app.backup import run_backup
from app.db import connect, init_db


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "tsumiki.db"
    conn = connect(path)
    init_db(conn)
    conn.execute(
        """
        INSERT INTO tasks (title, state, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        ("バックアップ対象タスク", "inbox", "2026-09-01T00:00:00Z", "2026-09-01T00:00:00Z"),
    )
    conn.commit()
    conn.close()
    return path


def test_first_backup_creates_file(db_path, tmp_path):
    backup_dir = tmp_path / "backups"
    result = run_backup(db_path, backup_dir, keep=7)

    assert result is not None
    assert result.exists()
    assert result.name == f"{date.today().isoformat()}.db"


def test_second_backup_same_day_returns_none(db_path, tmp_path):
    backup_dir = tmp_path / "backups"
    first = run_backup(db_path, backup_dir, keep=7)
    files_after_first = list(backup_dir.glob("*.db"))

    second = run_backup(db_path, backup_dir, keep=7)
    files_after_second = list(backup_dir.glob("*.db"))

    assert first is not None
    assert second is None
    assert len(files_after_second) == len(files_after_first) == 1


def test_prune_keeps_only_latest_n(db_path, tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True)

    # 過去10日分のダミーバックアップを事前に用意しておく
    for day in range(1, 11):
        (backup_dir / f"2020-01-{day:02d}.db").write_bytes(b"")

    run_backup(db_path, backup_dir, keep=7)

    remaining = sorted(p.name for p in backup_dir.glob("*.db"))
    # 今日の分 + 直近6件の過去ダミー(01-05 ～ 01-10) = 7件
    assert len(remaining) == 7
    assert "2020-01-01.db" not in remaining
    assert "2020-01-04.db" not in remaining
    assert "2020-01-05.db" in remaining
    assert "2020-01-10.db" in remaining
    assert f"{date.today().isoformat()}.db" in remaining


def test_backup_file_is_readable_and_has_original_data(db_path, tmp_path):
    backup_dir = tmp_path / "backups"
    result = run_backup(db_path, backup_dir, keep=7)

    conn = sqlite3.connect(str(result))
    row = conn.execute("SELECT title FROM tasks").fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "バックアップ対象タスク"


def test_backup_directory_and_file_permissions_are_restricted(db_path, tmp_path):
    # B1: バックアップ先ディレクトリ 0700・バックアップファイル 0600。
    # 既存の緩いディレクトリでも chmod されることを確認する
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(mode=0o755)

    result = run_backup(db_path, backup_dir, keep=7)

    dir_mode = stat.S_IMODE(backup_dir.stat().st_mode)
    file_mode = stat.S_IMODE(result.stat().st_mode)
    assert dir_mode == 0o700
    assert file_mode == 0o600
