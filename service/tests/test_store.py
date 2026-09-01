import pytest

from app.db import connect, init_db
from app.models import InvalidTransition, State, TaskCreate, TaskUpdate
from app.store import TaskNotFound, TaskStore


@pytest.fixture
def store(tmp_path):
    conn = connect(tmp_path / "tsumiki.db")
    init_db(conn)
    yield TaskStore(conn)
    conn.close()


def test_add_and_get(store):
    task = store.add(TaskCreate(title="牛乳を買う"))
    assert task.id is not None
    assert task.title == "牛乳を買う"
    assert task.state == State.inbox
    assert task.created_at == task.updated_at
    assert task.completed_at is None

    fetched = store.get(task.id)
    assert fetched == task


def test_get_missing_returns_none(store):
    assert store.get(9999) is None


def test_add_with_explicit_state(store):
    task = store.add(TaskCreate(title="レビュー依頼", state=State.waiting, context="@office"))
    assert task.state == State.waiting
    assert task.context == "@office"


def test_list_filters_by_state(store):
    store.add(TaskCreate(title="A", state=State.inbox))
    store.add(TaskCreate(title="B", state=State.next))
    store.add(TaskCreate(title="C", state=State.next))

    next_tasks = store.list(state=State.next)
    assert {t.title for t in next_tasks} == {"B", "C"}

    inbox_tasks = store.list(state=State.inbox)
    assert {t.title for t in inbox_tasks} == {"A"}


def test_list_filters_by_context(store):
    store.add(TaskCreate(title="A", context="@home"))
    store.add(TaskCreate(title="B", context="@office"))
    store.add(TaskCreate(title="C", context="@home"))

    home_tasks = store.list(context="@home")
    assert {t.title for t in home_tasks} == {"A", "C"}


def test_list_filters_by_project(store):
    conn = store._conn
    now = "2026-09-01T00:00:00Z"
    cur = conn.execute(
        "INSERT INTO projects (name, note, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("プロジェクトX", None, now, now),
    )
    conn.commit()
    project_id = cur.lastrowid

    store.add(TaskCreate(title="紐づくタスク", project_id=project_id))
    store.add(TaskCreate(title="紐づかないタスク"))

    results = store.list(project_id=project_id)
    assert [t.title for t in results] == ["紐づくタスク"]


def test_list_filters_by_due_before(store):
    store.add(TaskCreate(title="早い", due="2026-09-01T00:00:00Z"))
    store.add(TaskCreate(title="遅い", due="2026-12-01T00:00:00Z"))
    store.add(TaskCreate(title="期限なし"))

    results = store.list(due_before="2026-10-01T00:00:00Z")
    assert [t.title for t in results] == ["早い"]


def test_list_order_by_state_then_due_then_created(store):
    # state の自然順: inbox, next, waiting, someday, done
    d = store.add(TaskCreate(title="done-task", state=State.done))
    c = store.add(TaskCreate(title="someday-task", state=State.someday))
    b = store.add(TaskCreate(title="next-no-due", state=State.next))
    a1 = store.add(TaskCreate(title="next-due-later", state=State.next, due="2026-10-01T00:00:00Z"))
    a2 = store.add(TaskCreate(title="next-due-earlier", state=State.next, due="2026-09-05T00:00:00Z"))

    results = store.list()
    titles = [t.title for t in results]
    # next 状態内: due あり(昇順) → due なしは最後
    assert titles == [
        "next-due-earlier",
        "next-due-later",
        "next-no-due",
        "someday-task",
        "done-task",
    ]


def test_list_order_covers_all_five_states(store):
    # B9: inbox/waiting を含む5状態すべてを入れて state の CASE 順を固定する
    # (以前のテストは next/someday/done しか無く、inbox<->waiting の入れ替えを検出できなかった)
    store.add(TaskCreate(title="done-task", state=State.done))
    store.add(TaskCreate(title="someday-task", state=State.someday))
    store.add(TaskCreate(title="waiting-task", state=State.waiting))
    store.add(TaskCreate(title="next-task", state=State.next))
    store.add(TaskCreate(title="inbox-task", state=State.inbox))

    titles = [t.title for t in store.list()]
    assert titles == [
        "inbox-task",
        "next-task",
        "waiting-task",
        "someday-task",
        "done-task",
    ]


def test_list_order_tiebreak_by_id_when_created_at_equal(store):
    # B9: created_at が同一(ミリ秒解像度の衝突を想定)の場合、id 昇順にフォールバックすること。
    # _now() のミリ秒解像度でレースさせるのではなく、直接 SQL で同一 created_at を作る。
    conn = store._conn
    same_ts = "2026-09-01T00:00:00.000Z"
    conn.execute(
        """
        INSERT INTO tasks (title, state, created_at, updated_at)
        VALUES (?, 'inbox', ?, ?)
        """,
        ("second-inserted", same_ts, same_ts),
    )
    conn.execute(
        """
        INSERT INTO tasks (title, state, created_at, updated_at)
        VALUES (?, 'inbox', ?, ?)
        """,
        ("first-inserted", same_ts, same_ts),
    )
    conn.commit()

    results = store.list()
    ids = [t.id for t in results]
    titles = [t.title for t in results]
    assert ids == sorted(ids)
    assert titles == ["second-inserted", "first-inserted"]


def test_list_limit_and_offset(store):
    for i in range(5):
        store.add(TaskCreate(title=f"task-{i}"))

    page1 = store.list(limit=2, offset=0)
    page2 = store.list(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert {t.id for t in page1}.isdisjoint({t.id for t in page2})


def test_update_fields(store):
    task = store.add(TaskCreate(title="元のタイトル"))
    updated = store.update(task.id, TaskUpdate(title="新しいタイトル", body="詳細"))
    assert updated.title == "新しいタイトル"
    assert updated.body == "詳細"
    assert updated.updated_at >= task.updated_at


def test_update_treats_explicit_none_fields_as_no_change(store):
    # B10: mcp_server.py は TaskUpdate の全フィールドを明示 kwarg で渡すため、
    # client.py の exclude_unset=True が効かず {"body": null, ...} も送信される。
    # 現状は「None = 変更なし」という意味論なので無害だが、将来 null=クリアに
    # 仕様変更したときに MCP 経由の更新が他フィールドを消す事故を防ぐため、
    # この意味論をテストで固定しておく。
    task = store.add(
        TaskCreate(
            title="元タイトル",
            body="元の本文",
            context="@home",
            due="2026-09-01T00:00:00Z",
        )
    )

    updated = store.update(
        task.id,
        TaskUpdate(
            title="新タイトル",
            body=None,
            state=None,
            project_id=None,
            context=None,
            due=None,
        ),
    )

    assert updated.title == "新タイトル"
    assert updated.body == "元の本文"
    assert updated.context == "@home"
    assert updated.due == "2026-09-01T00:00:00Z"


def test_update_valid_state_transition(store):
    task = store.add(TaskCreate(title="タスク", state=State.inbox))
    updated = store.update(task.id, TaskUpdate(state=State.next))
    assert updated.state == State.next


def test_update_invalid_state_transition_raises(store):
    task = store.add(TaskCreate(title="タスク", state=State.done))
    with pytest.raises(InvalidTransition):
        store.update(task.id, TaskUpdate(state=State.waiting))
    # 状態は変わっていないこと
    assert store.get(task.id).state == State.done


def test_update_same_state_raises(store):
    task = store.add(TaskCreate(title="タスク", state=State.inbox))
    with pytest.raises(InvalidTransition):
        store.update(task.id, TaskUpdate(state=State.inbox))


def test_update_with_no_fields_still_bumps_updated_at(store):
    task = store.add(TaskCreate(title="タスク"))
    updated = store.update(task.id, TaskUpdate())
    assert updated.title == task.title
    assert updated.updated_at >= task.updated_at


def test_update_missing_task_raises(store):
    with pytest.raises(TaskNotFound):
        store.update(9999, TaskUpdate(title="x"))


def test_update_to_done_sets_completed_at(store):
    # A1: complete() を経由しない update(state=done) でも completed_at が入ること
    task = store.add(TaskCreate(title="タスク", state=State.next))
    assert task.completed_at is None
    updated = store.update(task.id, TaskUpdate(state=State.done))
    assert updated.state == State.done
    assert updated.completed_at is not None


def test_update_from_done_clears_completed_at(store):
    # A1: 完了済みを done -> next で戻すと completed_at が NULL に戻ること
    task = store.add(TaskCreate(title="タスク", state=State.next))
    completed = store.complete(task.id)
    assert completed.completed_at is not None

    back = store.update(task.id, TaskUpdate(state=State.next))
    assert back.state == State.next
    assert back.completed_at is None


def test_complete_sets_state_and_completed_at(store):
    task = store.add(TaskCreate(title="タスク", state=State.next))
    completed = store.complete(task.id)
    assert completed.state == State.done
    assert completed.completed_at is not None


def test_complete_missing_task_raises(store):
    with pytest.raises(TaskNotFound):
        store.complete(9999)


def test_complete_already_done_raises(store):
    task = store.add(TaskCreate(title="タスク", state=State.done))
    with pytest.raises(InvalidTransition):
        store.complete(task.id)


def test_delete(store):
    task = store.add(TaskCreate(title="消すタスク"))
    assert store.delete(task.id) is True
    assert store.get(task.id) is None
    assert store.delete(task.id) is False
