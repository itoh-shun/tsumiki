import pytest
from pydantic import ValidationError

from app.config import Settings


def test_backup_keep_accepts_positive_values():
    s = Settings(backup_keep=1)
    assert s.backup_keep == 1


def test_backup_keep_rejects_zero():
    # B2: 0 だと backup.py の _prune_old_backups が作った直後のファイルまで消してしまう
    with pytest.raises(ValidationError):
        Settings(backup_keep=0)


def test_backup_keep_rejects_negative():
    with pytest.raises(ValidationError):
        Settings(backup_keep=-1)
