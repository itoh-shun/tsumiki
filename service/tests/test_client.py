import httpx
import pytest

from app.client import (
    ConflictError,
    RemoteProjectNotFound,
    ServiceUnavailable,
    RemoteTaskNotFound,
    TsumikiApiError,
    TsumikiClient,
)
from app.models import ProjectCreate, TaskCreate, TaskUpdate

TASK_BODY = {
    "id": 1,
    "title": "牛乳を買う",
    "body": None,
    "state": "inbox",
    "project_id": None,
    "context": None,
    "due": None,
    "created_at": "2026-09-01T00:00:00Z",
    "updated_at": "2026-09-01T00:00:00Z",
    "completed_at": None,
}


def make_client(handler) -> TsumikiClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url="http://test")
    return TsumikiClient(client=http_client)


def test_health_success():
    def handler(request):
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok", "version": "0.1.0"})

    client = make_client(handler)
    assert client.health() == {"status": "ok", "version": "0.1.0"}


def test_add_task_success():
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/tasks"
        return httpx.Response(201, json=TASK_BODY)

    client = make_client(handler)
    task = client.add_task(TaskCreate(title="牛乳を買う"))
    assert task.id == 1
    assert task.title == "牛乳を買う"
    assert task.state.value == "inbox"


def test_list_tasks_builds_query_params():
    captured = {}

    def handler(request):
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[TASK_BODY])

    client = make_client(handler)
    tasks = client.list_tasks(state="next", context="@home", limit=5)
    assert len(tasks) == 1
    assert captured["params"] == {"state": "next", "context": "@home", "limit": "5"}


def test_update_task_success():
    def handler(request):
        assert request.method == "PATCH"
        body = {**TASK_BODY, "title": "更新後"}
        return httpx.Response(200, json=body)

    client = make_client(handler)
    task = client.update_task(1, TaskUpdate(title="更新後"))
    assert task.title == "更新後"


def test_delete_task_success():
    def handler(request):
        assert request.method == "DELETE"
        return httpx.Response(204)

    client = make_client(handler)
    client.delete_task(1)  # 例外が出なければ成功


def test_connect_error_raises_service_unavailable():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    client = make_client(handler)
    with pytest.raises(ServiceUnavailable):
        client.get_task(1)


def test_connect_timeout_raises_service_unavailable():
    def handler(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    client = make_client(handler)
    with pytest.raises(ServiceUnavailable):
        client.list_tasks()


def test_read_timeout_raises_service_unavailable():
    # B5: 接続はできたが応答が返らない(ReadTimeout)も接続不可と同じ扱いにする
    def handler(request):
        raise httpx.ReadTimeout("read timed out", request=request)

    client = make_client(handler)
    with pytest.raises(ServiceUnavailable):
        client.get_task(1)


def test_404_raises_task_not_found():
    def handler(request):
        return httpx.Response(404, json={"detail": "task not found"})

    client = make_client(handler)
    with pytest.raises(RemoteTaskNotFound):
        client.get_task(999)


def test_404_raises_project_not_found():
    def handler(request):
        return httpx.Response(404, json={"detail": "project not found"})

    client = make_client(handler)
    with pytest.raises(RemoteProjectNotFound):
        client.get_project(999)


def test_409_raises_conflict_error_with_message():
    def handler(request):
        return httpx.Response(
            409,
            json={
                "detail": {
                    "code": "invalid_transition",
                    "from": "done",
                    "to": "done",
                    "message": "このタスクは既に完了しています",
                }
            },
        )

    client = make_client(handler)
    with pytest.raises(ConflictError) as exc_info:
        client.complete_task(1)

    err = exc_info.value
    assert err.status_code == 409
    assert err.code == "invalid_transition"
    assert err.from_state == "done"
    assert err.to_state == "done"
    assert err.message == "このタスクは既に完了しています"


def test_add_project_conflict_error():
    def handler(request):
        return httpx.Response(
            409,
            json={"detail": {"code": "conflict", "message": "同じ名前のプロジェクトが既に存在します"}},
        )

    client = make_client(handler)
    with pytest.raises(ConflictError) as exc_info:
        client.add_project(ProjectCreate(name="重複"))
    assert exc_info.value.message == "同じ名前のプロジェクトが既に存在します"


def test_other_error_raises_generic_api_error():
    def handler(request):
        return httpx.Response(500, json={"detail": "internal error"})

    client = make_client(handler)
    with pytest.raises(TsumikiApiError) as exc_info:
        client.get_task(1)
    assert exc_info.value.status_code == 500
    assert not isinstance(exc_info.value, (RemoteTaskNotFound, ConflictError))
