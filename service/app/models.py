"""ドメインモデルと状態遷移ルール。"""

from enum import Enum

from pydantic import BaseModel


class State(str, Enum):
    inbox = "inbox"
    next = "next"
    waiting = "waiting"
    someday = "someday"
    done = "done"


class InvalidTransition(Exception):
    """許可されていない状態遷移が要求されたときに送出する。"""

    def __init__(self, src: "State", dst: "State"):
        self.src = src
        self.dst = dst
        super().__init__(f"cannot transition from {src.value!r} to {dst.value!r}")


# 状態遷移の許可表。done から waiting / someday へは直接戻せない。
# 同一状態への遷移も不許可。
ALLOWED_TRANSITIONS: dict[State, frozenset[State]] = {
    State.inbox: frozenset({State.next, State.waiting, State.someday, State.done}),
    State.next: frozenset({State.inbox, State.waiting, State.someday, State.done}),
    State.waiting: frozenset({State.inbox, State.next, State.someday, State.done}),
    State.someday: frozenset({State.inbox, State.next, State.waiting, State.done}),
    State.done: frozenset({State.inbox, State.next}),
}


def can_transition(src: State, dst: State) -> bool:
    return dst in ALLOWED_TRANSITIONS.get(src, frozenset())


def assert_transition(src: State, dst: State) -> None:
    if not can_transition(src, dst):
        raise InvalidTransition(src, dst)


class ProjectCreate(BaseModel):
    name: str
    note: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    note: str | None = None


class Project(BaseModel):
    id: int
    name: str
    note: str | None = None
    created_at: str
    updated_at: str


class TaskCreate(BaseModel):
    title: str
    body: str | None = None
    state: State = State.inbox
    project_id: int | None = None
    context: str | None = None
    due: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    state: State | None = None
    project_id: int | None = None
    context: str | None = None
    due: str | None = None


class Task(BaseModel):
    id: int
    title: str
    body: str | None = None
    state: State
    project_id: int | None = None
    context: str | None = None
    due: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None
