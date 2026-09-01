"""状態名の日本語表示と、英語/日本語どちらの表記も受け付ける入力パース。

CLI (app.cli) と MCP サーバ (app.mcp_server) の両方から使う共通ユーティリティ。
DESIGN.md の正典 (受信/次の行動/待ち/いつか/完了) に合わせて表示する。
"""

from app.models import State

STATE_LABELS: dict[State, str] = {
    State.inbox: "受信",
    State.next: "次の行動",
    State.waiting: "待ち",
    State.someday: "いつか",
    State.done: "完了",
}

STATE_ALIASES: dict[str, State] = {
    "inbox": State.inbox,
    "受信": State.inbox,
    "next": State.next,
    "次の行動": State.next,
    "waiting": State.waiting,
    "待ち": State.waiting,
    "someday": State.someday,
    "いつか": State.someday,
    "done": State.done,
    "完了": State.done,
}


class UnknownState(ValueError):
    """英語・日本語のどちらの表記でも解決できない状態名。"""


def parse_state(value: str) -> State:
    try:
        return STATE_ALIASES[value]
    except KeyError:
        raise UnknownState(
            f"不明な状態です: {value!r}"
            "（受信/次の行動/待ち/いつか/完了 または inbox/next/waiting/someday/done）"
        ) from None


def label(state: State) -> str:
    return STATE_LABELS[state]
