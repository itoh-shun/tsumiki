"""client.py と main.py の間の HTTP 契約を固定する統合テスト。

TsumikiClient に Starlette の TestClient (httpx.Client 互換) を注入し、実際の
FastAPI アプリを介して 404/409 の翻訳が正しく行われることを確認する。

`with TestClient(app)` は使わない: lifespan が実 settings.db_path (~/.tsumiki) を
掴んで run_backup まで走ってしまうため。dependency_overrides だけで DB を差し替える。
"""

import pytest
from starlette.testclient import TestClient

from app.client import ConflictError, RemoteTaskNotFound, TsumikiClient
from app.db import connect, init_db
from app.main import app, get_conn
from app.models import State, TaskCreate


@pytest.fixture
def tsumiki_client(tmp_path):
    # TestClient は ASGI アプリを別スレッドで(逐次に)実行するため、sqlite3 の
    # 「同一スレッドでしか使えない」制約に check_same_thread=False で対応する。
    # 呼び出しは常に同期的(並行アクセスなし)なので安全。
    conn = connect(tmp_path / "tsumiki.db", check_same_thread=False)
    init_db(conn)
    app.dependency_overrides[get_conn] = lambda: conn

    # with を使わない: lifespan (実 settings.db_path を掴む) を起動させないため
    test_client = TestClient(app, base_url="http://localhost")
    client = TsumikiClient(client=test_client)
    yield client

    app.dependency_overrides.clear()
    conn.close()


def test_get_task_404_translates_to_remote_task_not_found(tsumiki_client):
    with pytest.raises(RemoteTaskNotFound):
        tsumiki_client.get_task(9999)


def test_complete_already_done_translates_to_conflict_error(tsumiki_client):
    task = tsumiki_client.add_task(TaskCreate(title="契約テスト", state=State.done))

    with pytest.raises(ConflictError) as exc_info:
        tsumiki_client.complete_task(task.id)

    err = exc_info.value
    assert err.from_state == "done"
    assert err.to_state == "done"
    assert err.message == "このタスクは既に完了しています"
