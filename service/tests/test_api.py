import pytest
from httpx import ASGITransport, AsyncClient

from app.db import connect, init_db
from app.main import app, get_conn


@pytest.fixture
async def client(tmp_path):
    conn = connect(tmp_path / "tsumiki.db")
    init_db(conn)
    app.dependency_overrides[get_conn] = lambda: conn

    transport = ASGITransport(app=app)
    # base_url は TrustedHostMiddleware の allowed_hosts に含まれる必要がある
    async with AsyncClient(transport=transport, base_url="http://localhost") as ac:
        yield ac

    app.dependency_overrides.clear()
    conn.close()


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": "0.1.0"}


async def test_transitions_matches_allowed_transitions_table(client):
    # B: 遷移の許可表は models.py の ALLOWED_TRANSITIONS が唯一の定義。
    # /meta/transitions のレスポンスがそこから生成されていること(表の複製に
    # ずれが出ていないこと)を、表そのものと突き合わせて検証する。表を変えたら
    # このテストが自動で追随する。
    from app.models import ALLOWED_TRANSITIONS, State

    resp = await client.get("/meta/transitions")
    assert resp.status_code == 200
    body = resp.json()

    expected = {
        src.value: sorted(d.value for d in ALLOWED_TRANSITIONS.get(src, frozenset()))
        for src in State
    }
    actual = {k: sorted(v) for k, v in body.items()}
    assert actual == expected

    # done からは inbox / next にしか戻せない、という最も踏み外しやすい制約は
    # 名指しでも確認しておく。
    assert sorted(body["done"]) == ["inbox", "next"]


async def test_untrusted_host_header_is_rejected(client):
    # A2: DNS rebinding 対策。TrustedHostMiddleware が既知でない Host を 400 で弾くこと
    resp = await client.get("/health", headers={"Host": "evil.example.com"})
    assert resp.status_code == 400


async def test_create_get_update_delete_task(client):
    created = await client.post("/tasks", json={"title": "牛乳を買う"})
    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "牛乳を買う"
    assert body["state"] == "inbox"
    task_id = body["id"]

    fetched = await client.get(f"/tasks/{task_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == task_id

    updated = await client.patch(f"/tasks/{task_id}", json={"title": "牛乳とパンを買う"})
    assert updated.status_code == 200
    assert updated.json()["title"] == "牛乳とパンを買う"

    deleted = await client.delete(f"/tasks/{task_id}")
    assert deleted.status_code == 204

    missing = await client.get(f"/tasks/{task_id}")
    assert missing.status_code == 404


async def test_list_tasks_with_filters(client):
    await client.post("/tasks", json={"title": "A", "state": "inbox"})
    await client.post("/tasks", json={"title": "B", "state": "next"})
    await client.post("/tasks", json={"title": "C", "state": "next"})

    resp = await client.get("/tasks", params={"state": "next"})
    assert resp.status_code == 200
    titles = {t["title"] for t in resp.json()}
    assert titles == {"B", "C"}


async def test_list_tasks_with_combined_filters(client):
    await client.post(
        "/tasks",
        json={"title": "早い@home", "context": "@home", "due": "2026-09-01T00:00:00Z"},
    )
    await client.post(
        "/tasks",
        json={"title": "遅い@home", "context": "@home", "due": "2026-12-01T00:00:00Z"},
    )
    await client.post(
        "/tasks",
        json={"title": "早い@office", "context": "@office", "due": "2026-09-01T00:00:00Z"},
    )

    resp = await client.get(
        "/tasks",
        params={
            "context": "@home",
            "due_before": "2026-10-01T00:00:00Z",
            "limit": 1,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["title"] == "早い@home"


async def test_list_tasks_rejects_negative_limit(client):
    # B8: 負値の limit/offset は LIMIT -1 (全件) に化けるので 422 で弾く
    resp = await client.get("/tasks", params={"limit": -1})
    assert resp.status_code == 422


async def test_list_tasks_rejects_zero_limit(client):
    resp = await client.get("/tasks", params={"limit": 0})
    assert resp.status_code == 422


async def test_list_tasks_rejects_negative_offset(client):
    resp = await client.get("/tasks", params={"offset": -1})
    assert resp.status_code == 422


async def test_get_task_404(client):
    resp = await client.get("/tasks/9999")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "task not found"}


async def test_update_task_404(client):
    resp = await client.patch("/tasks/9999", json={"title": "x"})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "task not found"}


async def test_delete_task_404(client):
    resp = await client.delete("/tasks/9999")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "task not found"}


async def test_complete_task(client):
    created = await client.post("/tasks", json={"title": "レポート提出", "state": "next"})
    task_id = created.json()["id"]

    resp = await client.post(f"/tasks/{task_id}/complete")
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "done"
    assert body["completed_at"] is not None


async def test_complete_already_done_returns_409(client):
    created = await client.post("/tasks", json={"title": "済みタスク", "state": "done"})
    task_id = created.json()["id"]

    resp = await client.post(f"/tasks/{task_id}/complete")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "invalid_transition"
    assert detail["from"] == "done"
    assert detail["to"] == "done"
    assert "既に完了しています" in detail["message"]


async def test_invalid_state_transition_returns_409(client):
    created = await client.post("/tasks", json={"title": "済みタスク2", "state": "done"})
    task_id = created.json()["id"]

    resp = await client.patch(f"/tasks/{task_id}", json={"state": "waiting"})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "invalid_transition"
    assert detail["from"] == "done"
    assert detail["to"] == "waiting"
    # done からの不許可遷移は「受信」または「次の行動」にしか戻せない旨の日本語で説明されること
    assert "完了済み" in detail["message"]
    assert "waiting" not in detail["message"]


async def test_same_state_transition_message_is_japanese(client):
    created = await client.post("/tasks", json={"title": "同一状態", "state": "next"})
    task_id = created.json()["id"]

    resp = await client.patch(f"/tasks/{task_id}", json={"state": "next"})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["from"] == "next"
    assert detail["to"] == "next"
    # 英語の state 値がそのままメッセージに混ざらないこと
    assert "next" not in detail["message"]
    assert "次の行動" in detail["message"]


async def test_task_with_nonexistent_project_id_returns_409_not_project_conflict(client):
    resp = await client.post("/tasks", json={"title": "存在しないプロジェクト", "project_id": 999})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "conflict"
    assert "プロジェクトが存在しません" in detail["message"]
    assert "同じ名前" not in detail["message"]


async def test_validation_error_returns_422(client):
    resp = await client.post("/tasks", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"][0]["loc"] == ["body", "title"]
    assert body["detail"][0]["type"] == "missing"


async def test_projects_crud(client):
    created = await client.post("/projects", json={"name": "旅行の計画"})
    assert created.status_code == 201
    project_id = created.json()["id"]

    listed = await client.get("/projects")
    assert listed.status_code == 200
    assert any(p["id"] == project_id for p in listed.json())

    updated = await client.patch(f"/projects/{project_id}", json={"note": "来月まで"})
    assert updated.status_code == 200
    assert updated.json()["note"] == "来月まで"

    deleted = await client.delete(f"/projects/{project_id}")
    assert deleted.status_code == 204

    missing = await client.get(f"/projects/{project_id}")
    assert missing.status_code == 404


async def test_project_not_found_404(client):
    resp = await client.get("/projects/9999")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "project not found"}


async def test_duplicate_project_name_returns_409(client):
    first = await client.post("/projects", json={"name": "重複プロジェクト"})
    assert first.status_code == 201

    dup = await client.post("/projects", json={"name": "重複プロジェクト"})
    assert dup.status_code == 409
    assert dup.json()["detail"]["code"] == "conflict"
