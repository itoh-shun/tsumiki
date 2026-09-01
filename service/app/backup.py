"""日次バックアップ。SQLite のバックアップ API を使い、WAL 使用中でも安全にコピーする。"""

import os
import sqlite3
from datetime import date
from pathlib import Path


def run_backup(db_path: str | Path, backup_dir: str | Path, keep: int) -> Path | None:
    """当日分のバックアップが無ければ作成し、古いバックアップを keep 件まで間引く。

    当日分が既にあれば何もせず None を返す。
    """
    backup_dir = Path(backup_dir).expanduser()
    backup_dir.mkdir(parents=True, exist_ok=True)
    # mkdir(exist_ok=True) は既存ディレクトリの mode を変えないので明示的に chmod する(B1)
    os.chmod(backup_dir, 0o700)

    dest = backup_dir / f"{date.today().isoformat()}.db"
    if dest.exists():
        return None

    src_conn = sqlite3.connect(str(Path(db_path).expanduser()))
    try:
        dest_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()

    # バックアップ先ファイルにはタスクの本文が丸ごと入るので 0600 に絞る
    os.chmod(dest, 0o600)

    _prune_old_backups(backup_dir, keep)
    return dest


def _prune_old_backups(backup_dir: Path, keep: int) -> None:
    # ファイル名が YYYY-MM-DD.db なので文字列の降順ソート = 新しい順
    backups = sorted(backup_dir.glob("*.db"), reverse=True)
    for old in backups[keep:]:
        old.unlink()
