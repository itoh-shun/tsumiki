import stat

from app.main import _prepare_log_file


def test_prepare_log_file_sets_restrictive_permissions(tmp_path):
    # B1: ログディレクトリ 0700・ログファイル 0600。
    # RotatingFileHandler は dictConfig 経由で生成されるため、事前にここで用意する。
    log_dir = tmp_path / "logs"
    log_dir.mkdir(mode=0o755)  # あえて緩いパーミッションで事前に作っておく

    _prepare_log_file(log_dir)

    log_file = log_dir / "service.log"
    assert log_file.exists()

    dir_mode = stat.S_IMODE(log_dir.stat().st_mode)
    file_mode = stat.S_IMODE(log_file.stat().st_mode)
    assert dir_mode == 0o700
    assert file_mode == 0o600


def test_prepare_log_file_is_idempotent(tmp_path):
    log_dir = tmp_path / "logs"
    _prepare_log_file(log_dir)
    _prepare_log_file(log_dir)  # 2回目でも例外にならない

    log_file = log_dir / "service.log"
    assert log_file.exists()
