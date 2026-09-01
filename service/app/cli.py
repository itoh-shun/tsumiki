"""tsumiki CLI。DB を直接触らず、必ず TsumikiClient 経由で tsumiki-service を叩く。"""

from typing import Callable, NoReturn, Optional, TypeVar

import typer

from app.client import (
    ConflictError,
    RemoteTaskNotFound,
    ServiceUnavailable,
    TsumikiApiError,
    TsumikiClient,
)
from app.models import State, Task, TaskCreate, TaskUpdate
from app.state_labels import UnknownState, label, parse_state

app = typer.Typer(help="tsumiki: ローカル完結のタスク管理 CLI")

T = TypeVar("T")


def _client() -> TsumikiClient:
    return TsumikiClient()


def _parse_state_option(value: str) -> State:
    try:
        return parse_state(value)
    except UnknownState as e:
        raise typer.BadParameter(str(e)) from e


def _fail_service_unavailable() -> NoReturn:
    typer.echo(
        "tsumiki-service が起動していません。`uv run tsumiki-service` で起動してください",
        err=True,
    )
    raise typer.Exit(code=1)


def _fail_task_not_found(task_id: int) -> NoReturn:
    typer.echo(f"タスク #{task_id} は見つかりません", err=True)
    raise typer.Exit(code=1)


def _fail_conflict(exc: ConflictError) -> NoReturn:
    typer.echo(exc.message or str(exc), err=True)
    raise typer.Exit(code=1)


def _fail_api_error(exc: TsumikiApiError) -> NoReturn:
    typer.echo(
        f"tsumiki-service がエラーを返しました (status={exc.status_code}): {exc.body}",
        err=True,
    )
    raise typer.Exit(code=1)


def _call(fn: Callable[[], T], *, not_found_task_id: Optional[int] = None) -> T:
    """client 呼び出しを1箇所で実行し、例外を CLI の終了処理に翻訳する共通ハンドラ。

    6コマンドに重複していた except の階段をここに畳んである。
    """
    try:
        return fn()
    except ServiceUnavailable:
        _fail_service_unavailable()
    except RemoteTaskNotFound:
        if not_found_task_id is not None:
            _fail_task_not_found(not_found_task_id)
        raise
    except ConflictError as e:
        _fail_conflict(e)
    except TsumikiApiError as e:
        _fail_api_error(e)


def _print_task(task: Task) -> None:
    line = f"#{task.id} [{label(task.state)}] {task.title}"
    if task.context:
        line += f" ({task.context})"
    if task.due:
        line += f" due:{task.due}"
    typer.echo(line)


@app.command()
def add(
    title: str,
    state: str = typer.Option(
        "受信", "--state", help="受信/次の行動/待ち/いつか/完了 または inbox/next/waiting/someday/done"
    ),
    context: Optional[str] = typer.Option(None, "--context", help="コンテキスト(例: @home)"),
    due: Optional[str] = typer.Option(None, "--due", help="期限(ISO 8601)"),
    project: Optional[int] = typer.Option(None, "--project", help="プロジェクト id"),
) -> None:
    """タスクを追加する。"""
    parsed_state = _parse_state_option(state)
    with _client() as client:
        task = _call(
            lambda: client.add_task(
                TaskCreate(
                    title=title,
                    state=parsed_state,
                    context=context,
                    due=due,
                    project_id=project,
                )
            )
        )
    _print_task(task)


@app.command()
def ls(
    state: Optional[str] = typer.Option(None, "--state"),
    context: Optional[str] = typer.Option(None, "--context"),
    project: Optional[int] = typer.Option(None, "--project"),
    limit: Optional[int] = typer.Option(None, "--limit"),
) -> None:
    """タスク一覧を表示する。"""
    parsed_state = _parse_state_option(state) if state is not None else None
    with _client() as client:
        tasks = _call(
            lambda: client.list_tasks(
                state=parsed_state, context=context, project_id=project, limit=limit
            )
        )

    if not tasks:
        typer.echo("タスクはありません")
        return
    for task in tasks:
        _print_task(task)


@app.command()
def show(task_id: int) -> None:
    """タスクの詳細を表示する。"""
    with _client() as client:
        task = _call(lambda: client.get_task(task_id), not_found_task_id=task_id)
    _print_task(task)
    if task.body:
        typer.echo(task.body)


@app.command()
def done(task_id: int) -> None:
    """タスクを完了にする。"""
    with _client() as client:
        task = _call(lambda: client.complete_task(task_id), not_found_task_id=task_id)
    _print_task(task)


@app.command()
def mv(task_id: int, state: str) -> None:
    """タスクの状態を移す。"""
    parsed_state = _parse_state_option(state)
    with _client() as client:
        task = _call(
            lambda: client.update_task(task_id, TaskUpdate(state=parsed_state)),
            not_found_task_id=task_id,
        )
    _print_task(task)


@app.command()
def rm(task_id: int) -> None:
    """タスクを削除する。"""
    with _client() as client:
        _call(lambda: client.delete_task(task_id), not_found_task_id=task_id)
    typer.echo(f"タスク #{task_id} を削除しました")


if __name__ == "__main__":
    app()
