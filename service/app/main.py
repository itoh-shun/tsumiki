"""FastAPI アプリ本体。"""

import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, Query
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.backup import run_backup
from app.config import settings
from app.db import connect, init_db
from app.models import (
    ALLOWED_TRANSITIONS,
    InvalidTransition,
    Project,
    ProjectCreate,
    ProjectUpdate,
    State,
    Task,
    TaskCreate,
    TaskUpdate,
)
from app.state_labels import STATE_LABELS
from app.store import ProjectNotFound, ProjectStore, TaskNotFound, TaskStore

logger = logging.getLogger("tsumiki")

VERSION = "0.1.0"

# ループバック以外に bind するのは、利用者自身のブラウザを DNS rebinding で
# 踏み台にされる経路を開く。既定では拒否し、opt-in の環境変数がある時だけ許可する。
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _check_host_is_loopback() -> None:
    if settings.host in LOOPBACK_HOSTS:
        return
    if os.getenv("TSUMIKI_ALLOW_NON_LOOPBACK") == "1":
        logger.warning(
            "settings.host=%r はループバックアドレスではありませんが、"
            "TSUMIKI_ALLOW_NON_LOOPBACK=1 が指定されているため起動を継続します",
            settings.host,
        )
        return
    raise RuntimeError(
        f"settings.host={settings.host!r} はループバックアドレスではありません。"
        " 意図的に外部へ公開する場合のみ環境変数 TSUMIKI_ALLOW_NON_LOOPBACK=1 を設定してください。"
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # mcp_smoke.py のように uvicorn を直接起動する経路もあるため、run() ではなく
    # ここ(lifespan)でチェックする。両方の起動経路を確実に通る。
    _check_host_is_loopback()

    conn = connect(settings.db_path)
    init_db(conn)
    app.state.conn = conn
    try:
        run_backup(settings.db_path, settings.backup_dir, settings.backup_keep)
    except Exception:
        # バックアップの失敗でアプリ起動を落とさない。ログにだけ残す
        logger.exception("daily backup failed")
    yield
    conn.close()


app = FastAPI(title="tsumiki-service", lifespan=lifespan)
# DNS rebinding 対策: 利用者のブラウザが外部サイトから同一オリジンとして
# このサービスを叩けてしまう経路を Host ヘッダ検証で塞ぐ。
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])


def get_conn() -> sqlite3.Connection:
    """DB 接続を返す依存性。テストでは dependency_overrides で差し替える。"""
    conn = getattr(app.state, "conn", None)
    if conn is None:
        raise RuntimeError("database connection is not initialized")
    return conn


def get_task_store(conn: sqlite3.Connection = Depends(get_conn)) -> TaskStore:
    return TaskStore(conn)


def get_project_store(conn: sqlite3.Connection = Depends(get_conn)) -> ProjectStore:
    return ProjectStore(conn)


@app.exception_handler(TaskNotFound)
async def task_not_found_handler(request, exc: TaskNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "task not found"})


@app.exception_handler(ProjectNotFound)
async def project_not_found_handler(request, exc: ProjectNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "project not found"})


@app.exception_handler(sqlite3.IntegrityError)
async def integrity_error_handler(request, exc: sqlite3.IntegrityError) -> JSONResponse:
    # UNIQUE (projects.name の重複) と FOREIGN KEY (存在しない project_id 指定) の
    # どちらでも起こり得るので、メッセージで区別して読める説明を返す
    reason = str(exc)
    if "FOREIGN KEY" in reason:
        message = "指定されたプロジェクトが存在しません"
    elif "UNIQUE" in reason:
        message = "同じ名前のプロジェクトが既に存在します"
    else:
        message = "データの整合性エラーが発生しました"
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "code": "conflict",
                "message": message,
            }
        },
    )


def _allowed_destinations_label(src: State) -> str | None:
    """models.py の許可表から `src` の遷移先一覧を日本語ラベルの文で組み立てる。

    文言をここで手書きせず表から生成することで、許可表を変えたら文言が自動で
    追随するようにする(B3)。State の正典順で並べ、複数あれば「または」で繋ぐ。
    """
    dests = [s for s in list(State) if s in ALLOWED_TRANSITIONS.get(src, frozenset())]
    if not dests:
        return None
    labels = [f"「{STATE_LABELS[d]}」" for d in dests]
    if len(labels) == 1:
        return labels[0]
    return "、".join(labels[:-1]) + "または" + labels[-1]


@app.exception_handler(InvalidTransition)
async def invalid_transition_handler(request, exc: InvalidTransition) -> JSONResponse:
    if exc.src == State.done and exc.dst == State.done:
        message = "このタスクは既に完了しています"
    elif exc.src == State.done:
        message = f"完了済みのタスクは{_allowed_destinations_label(State.done)}にしか戻せません"
    elif exc.src == exc.dst:
        message = f"「{STATE_LABELS[exc.src]}」から同じ状態への変更はできません"
    else:
        message = f"「{STATE_LABELS[exc.src]}」から「{STATE_LABELS[exc.dst]}」への変更は許可されていません"
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "code": "invalid_transition",
                "from": exc.src.value,
                "to": exc.dst.value,
                "message": message,
            }
        },
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": VERSION}


@app.get("/meta/transitions")
async def transitions() -> dict[str, list[str]]:
    """状態遷移の許可表を読み取り専用で返す。

    `ALLOWED_TRANSITIONS`(models.py)が唯一の定義であり続けるよう、ここでは
    表を書き写さずそのまま JSON 化するだけにする。フロントエンドはこれを見て
    出せる遷移だけをメニューに出す(表の複製を持たない)。
    """
    return {
        src.value: [d.value for d in list(State) if d in ALLOWED_TRANSITIONS.get(src, frozenset())]
        for src in State
    }


# --- tasks --------------------------------------------------------------


@app.post("/tasks", response_model=Task, status_code=201)
async def create_task(
    data: TaskCreate, store: TaskStore = Depends(get_task_store)
) -> Task:
    return store.add(data)


@app.get("/tasks", response_model=list[Task])
async def list_tasks(
    state: State | None = None,
    context: str | None = None,
    project_id: int | None = None,
    due_before: str | None = None,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    store: TaskStore = Depends(get_task_store),
) -> list[Task]:
    return store.list(
        state=state,
        context=context,
        project_id=project_id,
        due_before=due_before,
        limit=limit,
        offset=offset,
    )


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int, store: TaskStore = Depends(get_task_store)) -> Task:
    task = store.get(task_id)
    if task is None:
        raise TaskNotFound(f"task {task_id} not found")
    return task


@app.patch("/tasks/{task_id}", response_model=Task)
async def update_task(
    task_id: int, data: TaskUpdate, store: TaskStore = Depends(get_task_store)
) -> Task:
    return store.update(task_id, data)


@app.post("/tasks/{task_id}/complete", response_model=Task)
async def complete_task(
    task_id: int, store: TaskStore = Depends(get_task_store)
) -> Task:
    return store.complete(task_id)


@app.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, store: TaskStore = Depends(get_task_store)) -> None:
    if not store.delete(task_id):
        raise TaskNotFound(f"task {task_id} not found")


# --- projects -------------------------------------------------------------


@app.post("/projects", response_model=Project, status_code=201)
async def create_project(
    data: ProjectCreate, store: ProjectStore = Depends(get_project_store)
) -> Project:
    return store.add(data)


@app.get("/projects", response_model=list[Project])
async def list_projects(store: ProjectStore = Depends(get_project_store)) -> list[Project]:
    return store.list()


@app.get("/projects/{project_id}", response_model=Project)
async def get_project(
    project_id: int, store: ProjectStore = Depends(get_project_store)
) -> Project:
    project = store.get(project_id)
    if project is None:
        raise ProjectNotFound(f"project {project_id} not found")
    return project


@app.patch("/projects/{project_id}", response_model=Project)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    store: ProjectStore = Depends(get_project_store),
) -> Project:
    return store.update(project_id, data)


@app.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: int, store: ProjectStore = Depends(get_project_store)
) -> None:
    if not store.delete(project_id):
        raise ProjectNotFound(f"project {project_id} not found")


def _build_log_config() -> dict:
    """uvicorn の既定ログ設定を差し替え、標準出力とログファイルの両方へ出す。

    uvicorn は自身のロガー(uvicorn / uvicorn.error / uvicorn.access)を
    propagate=False で構成するため、root への addHandler だけではアクセス
    ログ等がファイルに落ちない。ここでは dictConfig を直接組み立て、
    console と file の両ハンドラを全ロガーに紐付ける。
    """
    log_file = str(settings.log_dir / "service.log")
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": log_file,
                "maxBytes": 5_000_000,
                "backupCount": 3,
                "encoding": "utf-8",
                "formatter": "default",
            },
        },
        "root": {
            "handlers": ["console", "file"],
            "level": "INFO",
        },
        "loggers": {
            "uvicorn": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        },
    }


def _prepare_log_file(log_dir) -> None:
    """ログディレクトリ・ログファイルを 0700/0600 で用意する(B1)。

    RotatingFileHandler は dictConfig 経由で uvicorn 側が生成するため、生成後に
    こちらから chmod することができない。先にファイルを作って権限を絞ってから
    ハンドラに開かせる。mkdir(exist_ok=True) / touch(exist_ok=True) は既存の
    ディレクトリ・ファイルの mode を変えないので、いずれも明示的に chmod する。
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(log_dir, 0o700)

    log_file = log_dir / "service.log"
    log_file.touch(exist_ok=True)
    os.chmod(log_file, 0o600)


def run() -> None:
    """uvicorn でサービスを起動する。標準出力に加えてログファイルへローテーション付きで出力する。"""
    import uvicorn

    _prepare_log_file(settings.log_dir)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_config=_build_log_config(),
    )
