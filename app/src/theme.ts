// tsumiki 一覧ウィンドウ（List.tsx）専用の定数。DESIGN.md §2/§3/§4 から値を引く。
//
// Capture.tsx にも同じ値（FONT_STACK 等）が個別に定義されているが、あちらは
// 実機で7項目すべて検証済み・コミット済みのファイルなので、重複を消すために
// 手を入れることはしない。ここでは List.tsx 専用として独立に定義する。

export const FONT_STACK =
  '"Inter", "Noto Sans JP", -apple-system, system-ui, "Segoe UI", "Hiragino Sans", "Yu Gothic UI", "Meiryo", Helvetica, Arial';

// 等幅は技術的な文字列（キーバインド・ポート番号）にだけ使う（DESIGN.md §3）。
export const MONO_FONT_STACK =
  '"JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace';

export const SOFT_CARD_SHADOW =
  "rgba(0,0,0,0.04) 0px 4px 18px, rgba(0,0,0,0.027) 0px 2.025px 7.84688px, rgba(0,0,0,0.02) 0px 0.8px 2.925px, rgba(0,0,0,0.01) 0px 0.175px 1.04062px";

export type TaskState = "inbox" | "next" | "waiting" | "someday" | "done";

// 一覧ウィンドウのチップ・状態バーで使う順序。service/app/models.py の
// State と同じ5値（GTD の状態は5つ、順序も store.list() の並び順に合わせてある）。
export const STATE_ORDER: TaskState[] = [
  "inbox",
  "next",
  "waiting",
  "someday",
  "done",
];

// 状態名の日本語表示（service/app/state_labels.py の正典と一致させる）。
export const STATE_LABELS: Record<TaskState, string> = {
  inbox: "受信",
  next: "次の行動",
  waiting: "待ち",
  someday: "いつか",
  done: "完了",
};

// タスク行の状態バーの色（DESIGN.md §2「状態（GTD States）」）。
export const STATE_BAR_COLORS: Record<TaskState, string> = {
  inbox: "#d98324",
  next: "#31302e",
  waiting: "#615d59",
  someday: "#a39e98",
  done: "#1aae39",
};
