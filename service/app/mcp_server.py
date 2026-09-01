"""tsumiki MCP サーバ。DB を直接触らず、必ず T8 の TsumikiClient 経由で tsumiki-service を叩く。

stdio トランスポートで動く。`claude mcp add` などクライアント設定への登録はここでは行わない。
"""

from typing import Optional

from mcp.server import MCPServer

from app.client import (
    ConflictError,
    ServiceUnavailable,
    RemoteTaskNotFound,
    TsumikiApiError,
    TsumikiClient,
)
from app.models import Task, TaskCreate, TaskUpdate
from app.state_labels import UnknownState, parse_state

mcp = MCPServer("tsumiki")


def _client() -> TsumikiClient:
    return TsumikiClient()


def _task_to_dict(task: Task) -> dict:
    return task.model_dump(mode="json")


def _service_unavailable() -> dict:
    return {"error": "tsumiki-service が起動していません。`uv run tsumiki-service` で起動してください"}


def _task_not_found(task_id: int) -> dict:
    return {"error": f"タスク #{task_id} は見つかりません"}


def _conflict(exc: ConflictError) -> dict:
    return {"error": exc.message or str(exc)}


def _api_error(exc: TsumikiApiError) -> dict:
    return {"error": f"tsumiki-service がエラーを返しました (status={exc.status_code}): {exc.body}"}


@mcp.tool(
    description=(
        "タスクを新規に追加する。title は必須。state を省略すると「受信(inbox)」になる。"
        " state は inbox/next/waiting/someday/done、または受信/次の行動/待ち/いつか/完了のどちらでも指定できる。"
    )
)
def add_task(
    title: str,
    state: str = "inbox",
    context: Optional[str] = None,
    due: Optional[str] = None,
    project_id: Optional[int] = None,
) -> dict:
    try:
        parsed_state = parse_state(state)
    except UnknownState as e:
        return {"error": str(e)}

    with _client() as client:
        try:
            task = client.add_task(
                TaskCreate(
                    title=title,
                    state=parsed_state,
                    context=context,
                    due=due,
                    project_id=project_id,
                )
            )
        except ServiceUnavailable:
            return _service_unavailable()
        except ConflictError as e:
            return _conflict(e)
        except TsumikiApiError as e:
            return _api_error(e)
    return _task_to_dict(task)


@mcp.tool(
    description=(
        "タスク一覧を取得する。state / context / project_id / limit で絞り込める。"
        " state は inbox/next/waiting/someday/done、または受信/次の行動/待ち/いつか/完了のどちらでも指定できる。"
    )
)
def list_tasks(
    state: Optional[str] = None,
    context: Optional[str] = None,
    project_id: Optional[int] = None,
    limit: Optional[int] = None,
) -> dict:
    parsed_state = None
    if state is not None:
        try:
            parsed_state = parse_state(state)
        except UnknownState as e:
            return {"error": str(e)}

    with _client() as client:
        try:
            tasks = client.list_tasks(
                state=parsed_state, context=context, project_id=project_id, limit=limit
            )
        except ServiceUnavailable:
            return _service_unavailable()
        except TsumikiApiError as e:
            return _api_error(e)
    return {"tasks": [_task_to_dict(t) for t in tasks]}


@mcp.tool(description="id を指定して単一のタスクの詳細を取得する。")
def get_task(task_id: int) -> dict:
    with _client() as client:
        try:
            task = client.get_task(task_id)
        except ServiceUnavailable:
            return _service_unavailable()
        except RemoteTaskNotFound:
            return _task_not_found(task_id)
        except TsumikiApiError as e:
            return _api_error(e)
    return _task_to_dict(task)


@mcp.tool(
    description=(
        "タスクのタイトル・本文・状態・コンテキスト・期限・所属プロジェクトを部分的に更新する。"
        " 渡さなかった項目は変更しない。"
    )
)
def update_task(
    task_id: int,
    title: Optional[str] = None,
    body: Optional[str] = None,
    state: Optional[str] = None,
    context: Optional[str] = None,
    due: Optional[str] = None,
    project_id: Optional[int] = None,
) -> dict:
    parsed_state = None
    if state is not None:
        try:
            parsed_state = parse_state(state)
        except UnknownState as e:
            return {"error": str(e)}

    with _client() as client:
        try:
            task = client.update_task(
                task_id,
                TaskUpdate(
                    title=title,
                    body=body,
                    state=parsed_state,
                    context=context,
                    due=due,
                    project_id=project_id,
                ),
            )
        except ServiceUnavailable:
            return _service_unavailable()
        except RemoteTaskNotFound:
            return _task_not_found(task_id)
        except ConflictError as e:
            return _conflict(e)
        except TsumikiApiError as e:
            return _api_error(e)
    return _task_to_dict(task)


@mcp.tool(description="タスクを完了状態にする。既に完了しているタスクに対しては、その旨のエラーを返す。")
def complete_task(task_id: int) -> dict:
    with _client() as client:
        try:
            task = client.complete_task(task_id)
        except ServiceUnavailable:
            return _service_unavailable()
        except RemoteTaskNotFound:
            return _task_not_found(task_id)
        except ConflictError as e:
            return _conflict(e)
        except TsumikiApiError as e:
            return _api_error(e)
    return _task_to_dict(task)


@mcp.tool(
    description=(
        "タスクの状態(受信/次の行動/待ち/いつか/完了)を移す。"
        " 許可されていない遷移(例: 完了から待ちへ戻す)を指定するとエラーを返す。"
    )
)
def move_state(task_id: int, state: str) -> dict:
    try:
        parsed_state = parse_state(state)
    except UnknownState as e:
        return {"error": str(e)}

    with _client() as client:
        try:
            task = client.update_task(task_id, TaskUpdate(state=parsed_state))
        except ServiceUnavailable:
            return _service_unavailable()
        except RemoteTaskNotFound:
            return _task_not_found(task_id)
        except ConflictError as e:
            return _conflict(e)
        except TsumikiApiError as e:
            return _api_error(e)
    return _task_to_dict(task)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
