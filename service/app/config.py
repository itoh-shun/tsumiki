import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    db_path: Path = Path(
        os.getenv("TSUMIKI_DB", "~/.tsumiki/tsumiki.db")
    ).expanduser()
    backup_dir: Path = Path(
        os.getenv("TSUMIKI_BACKUP_DIR", "~/.tsumiki/backups")
    ).expanduser()
    # 1 未満だと backup.py の _prune_old_backups が作った直後のファイルまで削除してしまう
    backup_keep: int = Field(default=int(os.getenv("TSUMIKI_BACKUP_KEEP", "7")), ge=1)
    log_dir: Path = Path(
        os.getenv("TSUMIKI_LOG_DIR", "~/.tsumiki/logs")
    ).expanduser()
    host: str = os.getenv("TSUMIKI_HOST", "127.0.0.1")
    port: int = int(os.getenv("TSUMIKI_PORT", "7331"))


settings = Settings()
