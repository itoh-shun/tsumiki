"""tsumiki-service への HTTP クライアント共有層。

CLI (app.cli) と MCP サーバ (app.mcp_server) はどちらも直接 DB を触らず、
必ずこのクライアント経由で tsumiki-service を叩く。サービスが唯一の書き込み口
という設計のため、接続できない場合にローカル DB へフォールバックすることは絶対にしない。
"""

from typing import Any

import httpx

from app.config import settings
from app.models import (
    Project,
    ProjectCreate,
    ProjectUpdate,
    State,
    Task,
    TaskCreate,
    TaskUpdate,
)


class ServiceUnavailable(Exception):
    """tsumiki-service に接続できないときに送出する。ローカル DB へのフォールバックは行わない。"""


class TsumikiApiError(Exception):
    """4xx/5xx のうち、専用の例外に翻訳されないもの。"""

    def __init__(self, status_code: int, body: Any):
        self.status_code = status_code
        self.body = body
        super().__init__(f"tsumiki API error {status_code}: {body!r}")


class RemoteTaskNotFound(TsumikiApiError):
    """タスクが存在しない(404)。

    `app.store.TaskNotFound` とは別物(こちらは HTTP レスポンス由来)。
    誤って store 版を import しても静かに通ってしまうのを防ぐため、あえて別名にしてある。
    """


class RemoteProjectNotFound(TsumikiApiError):
    """プロジェクトが存在しない(404)。`app.store.ProjectNotFound` とは別物。"""


class ConflictError(TsumikiApiError):
    """409。サーバの `detail` (code/from/to/message) を保持する。

    `from` / `to` は Python の予約語のため、属性名としてはそのまま使えない
    (`exc.from` は構文エラーになる)。そのため from_state / to_state という
    名前で保持する。生の detail は `detail` 属性からも参照できる。
    """

    def __init__(self, status_code: int, body: Any):
        super().__init__(status_code, body)
        detail = body.get("detail") if isinstance(body, dict) else None
        self.detail = detail
        if isinstance(detail, dict):
            self.code: str | None = detail.get("code")
            self.from_state: str | None = detail.get("from")
            self.to_state: str | None = detail.get("to")
            self.message: str | None = detail.get("message")
        else:
            self.code = None
            self.from_state = None
            self.to_state = None
            self.message = str(detail) if detail is not None else str(body)


def _state_value(state: State | str | None) -> str | None:
    if state is None:
        return None
    return state.value if isinstance(state, State) else state


class TsumikiClient:
    """REST API の各エンドポイントに1対1で対応するメソッドを持つ薄いクライアント。"""

    def __init__(
        self,
        base_url: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 5.0,
    ):
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            resolved = base_url or f"http://{settings.host}:{settings.port}"
            self._client = httpx.Client(base_url=resolved, timeout=timeout)
            self._owns_client = True

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "TsumikiClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        not_found_cls: type[TsumikiApiError] = TsumikiApiError,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            resp = self._client.request(method, path, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            raise ServiceUnavailable(f"tsumiki-service に接続できません: {e}") from e

        if resp.status_code < 400:
            return resp

        try:
            body: Any = resp.json()
        except Exception:
            body = resp.text

        if resp.status_code == 404:
            raise not_found_cls(resp.status_code, body)
        if resp.status_code == 409:
            raise ConflictError(resp.status_code, body)
        raise TsumikiApiError(resp.status_code, body)

    # --- misc -------------------------------------------------------------

    def health(self) -> dict:
        return self._request("GET", "/health").json()

    # --- tasks --------------------------------------------------------------

    def add_task(self, data: TaskCreate) -> Task:
        resp = self._request("POST", "/tasks", json=data.model_dump(mode="json"))
        return Task.model_validate(resp.json())

    def get_task(self, task_id: int) -> Task:
        resp = self._request(
            "GET", f"/tasks/{task_id}", not_found_cls=RemoteTaskNotFound
        )
        return Task.model_validate(resp.json())

    def list_tasks(
        self,
        *,
        state: State | str | None = None,
        context: str | None = None,
        project_id: int | None = None,
        due_before: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Task]:
        params: dict[str, Any] = {}
        if state is not None:
            params["state"] = _state_value(state)
        if context is not None:
            params["context"] = context
        if project_id is not None:
            params["project_id"] = project_id
        if due_before is not None:
            params["due_before"] = due_before
        if limit is not None:
            params["limit"] = limit
        if offset:
            params["offset"] = offset
        resp = self._request("GET", "/tasks", params=params)
        return [Task.model_validate(t) for t in resp.json()]

    def update_task(self, task_id: int, data: TaskUpdate) -> Task:
        resp = self._request(
            "PATCH",
            f"/tasks/{task_id}",
            json=data.model_dump(mode="json", exclude_unset=True),
            not_found_cls=RemoteTaskNotFound,
        )
        return Task.model_validate(resp.json())

    def complete_task(self, task_id: int) -> Task:
        resp = self._request(
            "POST", f"/tasks/{task_id}/complete", not_found_cls=RemoteTaskNotFound
        )
        return Task.model_validate(resp.json())

    def delete_task(self, task_id: int) -> None:
        self._request("DELETE", f"/tasks/{task_id}", not_found_cls=RemoteTaskNotFound)

    # --- projects -------------------------------------------------------------

    def add_project(self, data: ProjectCreate) -> Project:
        resp = self._request("POST", "/projects", json=data.model_dump(mode="json"))
        return Project.model_validate(resp.json())

    def get_project(self, project_id: int) -> Project:
        resp = self._request(
            "GET", f"/projects/{project_id}", not_found_cls=RemoteProjectNotFound
        )
        return Project.model_validate(resp.json())

    def list_projects(self) -> list[Project]:
        resp = self._request("GET", "/projects")
        return [Project.model_validate(p) for p in resp.json()]

    def update_project(self, project_id: int, data: ProjectUpdate) -> Project:
        resp = self._request(
            "PATCH",
            f"/projects/{project_id}",
            json=data.model_dump(mode="json", exclude_unset=True),
            not_found_cls=RemoteProjectNotFound,
        )
        return Project.model_validate(resp.json())

    def delete_project(self, project_id: int) -> None:
        self._request(
            "DELETE", f"/projects/{project_id}", not_found_cls=RemoteProjectNotFound
        )
