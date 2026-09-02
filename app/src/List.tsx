import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { fetch } from "@tauri-apps/plugin-http";
import {
  FONT_STACK,
  MONO_FONT_STACK,
  SOFT_CARD_SHADOW,
  STATE_BAR_COLORS,
  STATE_LABELS,
  STATE_ORDER,
  type TaskState,
} from "./theme";

// tsumiki 一覧ウィンドウ（DESIGN.md §4「一覧ウィンドウ（List Window）」
// 「タスク行（Task Row）」）。
// T17: 読んで見せるところまで。
// T18: 行の操作（完了トグル・状態を移す・削除）を追加。
// 遷移の許可表は service/app/models.py の ALLOWED_TRANSITIONS が唯一の定義。
// フロントには書き写さず、GET /meta/transitions を都度読む。

const CONNECTION_ERROR_MESSAGE =
  "サービスに繋がりません。tsumiki-service が起動しているか確認してください。";
const EMPTY_MESSAGE = "まだ何もありません。";

interface Task {
  id: number;
  title: string;
  state: TaskState;
  updated_at: string;
}

type TransitionTable = Record<TaskState, TaskState[]>;

const EMPTY_TRANSITIONS: TransitionTable = {
  inbox: [],
  next: [],
  waiting: [],
  someday: [],
  done: [],
};

async function getBaseUrl(): Promise<string> {
  return await invoke<string>("service_base_url");
}

async function fetchTasks(base: string, state: TaskState | null): Promise<Task[]> {
  const url = state ? `${base}/tasks?state=${state}` : `${base}/tasks`;
  const res = await fetch(url, { method: "GET", cache: "no-store" });
  if (!res.ok) {
    throw new Error(`http_error:${res.status}`);
  }
  const data = (await res.json()) as unknown;
  return Array.isArray(data) ? (data as Task[]) : [];
}

// GET /meta/transitions（models.py の ALLOWED_TRANSITIONS をそのまま JSON 化した
// もの）を読む。壊れた・想定外の形で返ってきた場合は「遷移なし」扱いにする。
// 許可されていない遷移を誤って出すより、メニューが空になる方がずっと安全。
async function fetchTransitions(base: string): Promise<TransitionTable> {
  const res = await fetch(`${base}/meta/transitions`, {
    method: "GET",
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`http_error:${res.status}`);
  }
  const data = (await res.json()) as unknown;
  const result: TransitionTable = { ...EMPTY_TRANSITIONS };
  if (!data || typeof data !== "object") return result;
  for (const state of STATE_ORDER) {
    const v = (data as Record<string, unknown>)[state];
    if (Array.isArray(v)) {
      result[state] = v.filter((s): s is TaskState =>
        (STATE_ORDER as string[]).includes(s as string),
      );
    }
  }
  return result;
}

function computeCounts(all: Task[]): Record<TaskState, number> {
  const counts: Record<TaskState, number> = {
    inbox: 0,
    next: 0,
    waiting: 0,
    someday: 0,
    done: 0,
  };
  for (const task of all) {
    counts[task.state] += 1;
  }
  return counts;
}

// 「たった今 / n分前 / n時間前 / n日前」、それより古いものは「M月D日」。
// 日数のしきい値は DESIGN.md に明記がないため、7日を境にした
// （直近1週間は相対表現の方が読みやすく、それより前は絶対日付の方が
// 位置づけが分かりやすいという一般的な目安）。
function formatRelativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "たった今";
  if (diffMin < 60) return `${diffMin}分前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}時間前`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 7) return `${diffDay}日前`;
  const d = new Date(iso);
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

// POST/PATCH/DELETE が失敗したときの日本語メッセージを組み立てる。
// 409（InvalidTransition・整合性エラー）はサーバ側が既に日本語の説明文
// （detail.message）を返すので、それをそのまま使う。他人のライブラリや
// サーバの不具合を私の側で言い換えて誤らせない。
async function describeError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as unknown;
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail: unknown }).detail;
      if (detail && typeof detail === "object" && "message" in detail) {
        const message = (detail as { message: unknown }).message;
        if (typeof message === "string") return message;
      }
      if (typeof detail === "string") return detail;
    }
  } catch {
    // JSON で返ってこなかった場合は下のフォールバックへ。
  }
  return `送信に失敗しました（サービスがエラーを返しました: ${res.status}）`;
}

export default function List() {
  const [selectedState, setSelectedState] = useState<TaskState | null>(null);
  const [rows, setRows] = useState<Task[]>([]);
  const [counts, setCounts] = useState<Record<TaskState, number> | null>(null);
  const [transitions, setTransitions] = useState<TransitionTable | null>(null);
  const [connectionError, setConnectionError] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [selectedRowId, setSelectedRowId] = useState<number | null>(null);
  const [connectionTarget, setConnectionTarget] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // list-opened はフォーカスの出入りなどで短時間に複数回飛ぶことがあり得る。
  // 古い応答が新しい応答より後に届いて上書きしないよう、直近の呼び出しだけを
  // 反映するトークンで守る（Capture.tsx の openTokenRef と同じ考え方）。
  const refreshTokenRef = useRef(0);
  // list-opened イベントのハンドラは購読時点の selectedState を古いまま
  // 閉じ込めてしまう（stale closure）ため、常に最新値を ref で持つ。
  const selectedStateRef = useRef<TaskState | null>(null);
  const actionErrorTimerRef = useRef<number | null>(null);

  useEffect(() => {
    selectedStateRef.current = selectedState;
  }, [selectedState]);

  const refresh = useCallback((state: TaskState | null) => {
    const token = ++refreshTokenRef.current;
    void (async () => {
      try {
        const base = await getBaseUrl();
        // チップの件数は常に全件から出す。表示行は選択中の状態があれば
        // サーバ側でフィルタし直す（?state=... を都度取り直す）。
        const all = await fetchTasks(base, null);
        if (refreshTokenRef.current !== token) return;
        setCounts(computeCounts(all));
        const displayRows = state === null ? all : await fetchTasks(base, state);
        if (refreshTokenRef.current !== token) return;
        setRows(displayRows);
        setConnectionError(false);

        // 遷移許可表も一覧と同じタイミングで取り直す。サービス起動直後など
        // 初回取得に失敗していても、次に開いたときに自然に回復する。
        try {
          const t = await fetchTransitions(base);
          if (refreshTokenRef.current === token) setTransitions(t);
        } catch (e) {
          console.error("failed to refresh allowed transitions", e);
        }
      } catch (e) {
        if (refreshTokenRef.current !== token) return;
        console.error("failed to refresh task list", e);
        // サービスが止まっているときに「0件です」に見せない。繋がらないと
        // 分かる表示にする。件数（チップ）も古い値を出し続けない。
        setConnectionError(true);
        setCounts(null);
        setRows([]);
      } finally {
        if (refreshTokenRef.current === token) setLoaded(true);
      }
    })();
  }, []);

  // 接続先の表示は service_base_url() が返すだけの純粋なローカル設定値で、
  // サービスの起動状態に依存しない。サービスが止まっていても出せるよう、
  // タスク一覧の取得とは別に取っておく。
  useEffect(() => {
    void (async () => {
      try {
        const base = await getBaseUrl();
        setConnectionTarget(base.replace(/^https?:\/\//, ""));
      } catch (e) {
        console.error("failed to resolve service base url", e);
      }
    })();
  }, []);

  useEffect(() => {
    refresh(selectedState);
  }, [selectedState, refresh]);

  useEffect(() => {
    // 一覧ウィンドウは hide()/show() を繰り返すだけで React コンポーネントは
    // マウントされ直されない（捕捉小窓の capture-opened と同じ理由）。
    // 表示されるたびに最新のタスク一覧を取り直す。
    const unlistenPromise = listen("list-opened", () =>
      refresh(selectedStateRef.current),
    );
    return () => {
      void unlistenPromise.then((unlisten) => unlisten());
    };
  }, [refresh]);

  useEffect(() => {
    return () => {
      if (actionErrorTimerRef.current !== null) {
        window.clearTimeout(actionErrorTimerRef.current);
      }
    };
  }, []);

  const showActionError = useCallback((message: string) => {
    setActionError(message);
    if (actionErrorTimerRef.current !== null) {
      window.clearTimeout(actionErrorTimerRef.current);
    }
    actionErrorTimerRef.current = window.setTimeout(() => {
      setActionError(null);
    }, 5000);
  }, []);

  // 行の操作（完了トグル・状態を移す・削除）の共通経路。
  // 楽観的更新はしない: 行を先に書き換えず、成功したときだけ一覧を取り直す。
  // こうすると「失敗したら元に戻す」ロールバックの作り込みが要らない
  // （成功する前に何も変えていないので、失敗時は何もしなければ既に正しい）。
  const runMutation = useCallback(
    async (send: (base: string) => Promise<Response>) => {
      try {
        const base = await getBaseUrl();
        const res = await send(base);
        if (!res.ok) {
          showActionError(await describeError(res));
          return;
        }
        setActionError(null);
        refresh(selectedStateRef.current);
      } catch (e) {
        console.error("action failed", e);
        showActionError(CONNECTION_ERROR_MESSAGE);
      }
    },
    [refresh, showActionError],
  );

  const toggleComplete = useCallback(
    (task: Task) => {
      void runMutation((base) =>
        task.state === "done"
          ? fetch(`${base}/tasks/${task.id}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ state: "inbox" }),
            })
          : fetch(`${base}/tasks/${task.id}/complete`, { method: "POST" }),
      );
    },
    [runMutation],
  );

  const changeTaskState = useCallback(
    (task: Task, dest: TaskState) => {
      void runMutation((base) =>
        fetch(`${base}/tasks/${task.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ state: dest }),
        }),
      );
    },
    [runMutation],
  );

  const deleteTask = useCallback(
    (task: Task) => {
      void runMutation((base) =>
        fetch(`${base}/tasks/${task.id}`, { method: "DELETE" }),
      );
    },
    [runMutation],
  );

  const toggleState = useCallback((state: TaskState) => {
    setSelectedState((prev) => (prev === state ? null : state));
  }, []);

  const toggleRowSelection = useCallback((id: number) => {
    setSelectedRowId((prev) => (prev === id ? null : id));
  }, []);

  return (
    <>
      {/*
        操作可能な要素すべてに focus outline を付ける（DESIGN.md §4/§7）。
        インライン style では :focus-visible を指定できないためここで。
        Capture.tsx の入力欄と違い、ここは outline を消さない。
        ポップオーバー（.tsumiki-popover）は document.body への portal で
        描画するため、.tsumiki-list-card の子孫にならない。別ルールで拾う。
      */}
      <style>{`
        .tsumiki-list-card button:focus-visible,
        .tsumiki-list-row:focus-visible,
        .tsumiki-popover button:focus-visible {
          outline: 2px solid #a8620f;
          outline-offset: -2px;
        }
      `}</style>
      <div
        style={{
          width: "100%",
          height: "100%",
          boxSizing: "border-box",
          padding: 32,
          background: "#f6f5f4",
          display: "flex",
        }}
      >
        <div
          className="tsumiki-list-card"
          style={{
            flex: 1,
            minWidth: 0,
            minHeight: 0,
            display: "flex",
            flexDirection: "column",
            background: "#ffffff",
            border: "1px solid rgba(0,0,0,0.1)",
            borderRadius: 12,
            boxShadow: SOFT_CARD_SHADOW,
            overflow: "hidden",
            fontFamily: FONT_STACK,
            fontFeatureSettings: '"lnum"',
          }}
        >
          <header
            style={{
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: 18,
              gap: 18,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 3,
                  flexShrink: 0,
                }}
                aria-hidden="true"
              >
                <div
                  style={{
                    width: 16,
                    height: 5,
                    borderRadius: 4,
                    background: "#d98324",
                  }}
                />
                <div
                  style={{
                    width: 16,
                    height: 5,
                    borderRadius: 4,
                    background: "#e8e4e0",
                  }}
                />
              </div>
              <span
                style={{
                  fontSize: 16,
                  fontWeight: 700,
                  lineHeight: 1.3,
                  letterSpacing: "-0.25px",
                  color: "rgba(0,0,0,0.95)",
                }}
              >
                tsumiki
              </span>
            </div>

            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "flex-end",
                gap: 6,
              }}
            >
              {STATE_ORDER.map((state) => (
                <StateChip
                  key={state}
                  state={state}
                  active={selectedState === state}
                  count={counts ? counts[state] : null}
                  onClick={() => toggleState(state)}
                />
              ))}
            </div>
          </header>

          {actionError && (
            <button
              type="button"
              onClick={() => setActionError(null)}
              style={{
                flexShrink: 0,
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "10px 18px",
                border: "none",
                borderBottom: "1px solid rgba(0,0,0,0.06)",
                background: "transparent",
                cursor: "pointer",
                textAlign: "left",
                fontFamily: "inherit",
                fontFeatureSettings: "inherit",
                fontSize: 13,
                fontWeight: 400,
                lineHeight: 1.43,
                color: "#615d59",
              }}
            >
              <WarningIcon />
              <span>{actionError}</span>
            </button>
          )}

          <div
            style={{
              flex: 1,
              minHeight: 0,
              overflowY: "auto",
            }}
          >
            {connectionError ? (
              <StatusLine text={CONNECTION_ERROR_MESSAGE} />
            ) : !loaded ? null : rows.length === 0 ? (
              <StatusLine text={EMPTY_MESSAGE} />
            ) : (
              rows.map((task, i) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  isLast={i === rows.length - 1}
                  selected={selectedRowId === task.id}
                  destinations={transitions ? transitions[task.state] : []}
                  onToggleSelect={() => toggleRowSelection(task.id)}
                  onToggleComplete={() => toggleComplete(task)}
                  onChangeState={(dest) => changeTaskState(task, dest)}
                  onDelete={() => deleteTask(task)}
                />
              ))
            )}
          </div>

          <footer
            style={{
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: 18,
              gap: 18,
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span
                style={{
                  fontFamily: MONO_FONT_STACK,
                  fontSize: 13,
                  color: "#615d59",
                }}
              >
                Alt+Shift+Space
              </span>
              <span style={{ fontSize: 13, fontWeight: 400, color: "#615d59" }}>
                捕捉
              </span>
            </span>
            <span
              style={{
                fontFamily: MONO_FONT_STACK,
                fontSize: 13,
                color: "#615d59",
              }}
            >
              {connectionTarget ?? ""}
            </span>
          </footer>
        </div>
      </div>
    </>
  );
}

function StatusLine({ text }: { text: string }) {
  // 空のとき・接続エラーのとき共通。#a39e98（Muted）は装飾専用なので使わない。
  // 読ませる文なので Secondary の下限 #615d59 で、控えめに1行だけ出す。
  return (
    <div
      style={{
        padding: "14px 18px",
        fontSize: 13,
        fontWeight: 400,
        lineHeight: 1.43,
        color: "#615d59",
      }}
    >
      {text}
    </div>
  );
}

// Capture.tsx のエラー表示と同じ意匠（円 + 縦棒 + 点）。新しい色相は足さず
// #a8620f（アクセント文字色）を使う。
function WarningIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      style={{ flexShrink: 0 }}
    >
      <circle cx="7" cy="7" r="6" stroke="#a8620f" strokeWidth="1.4" />
      <path d="M7 4V7.5" stroke="#a8620f" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="7" cy="9.8" r="0.9" fill="#a8620f" />
    </svg>
  );
}

function StateChip({
  state,
  active,
  count,
  onClick,
}: {
  state: TaskState;
  active: boolean;
  count: number | null;
  onClick: () => void;
}) {
  const [hover, setHover] = useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "inline-flex",
        flexShrink: 0,
        alignItems: "center",
        gap: 4,
        padding: "6px 12px",
        borderRadius: 9999,
        border: "none",
        cursor: "pointer",
        fontFamily: "inherit",
        fontFeatureSettings: "inherit",
        fontSize: 13,
        fontWeight: 600,
        lineHeight: 1.33,
        whiteSpace: "nowrap",
        background: active ? "#fdf3e8" : hover ? "rgba(0,0,0,0.03)" : "transparent",
        color: active ? "#a8620f" : "#615d59",
      }}
    >
      <span>{STATE_LABELS[state]}</span>
      {count !== null && <span>{count}</span>}
    </button>
  );
}

function TaskRow({
  task,
  isLast,
  selected,
  destinations,
  onToggleSelect,
  onToggleComplete,
  onChangeState,
  onDelete,
}: {
  task: Task;
  isLast: boolean;
  selected: boolean;
  destinations: TaskState[];
  onToggleSelect: () => void;
  onToggleComplete: () => void;
  onChangeState: (dest: TaskState) => void;
  onDelete: () => void;
}) {
  const [hover, setHover] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const isDone = task.state === "done";

  const openMenu = () => setMenuOpen(true);
  const closeMenu = () => setMenuOpen(false);

  const onIconClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggleComplete();
  };

  const onMenuButtonClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    openMenu();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter") {
      // 見た目上の選択トグル（T17 から引き継ぎ。今のところ副作用はない）。
      e.preventDefault();
      onToggleSelect();
    } else if (e.key === " ") {
      e.preventDefault();
      onToggleComplete();
    } else if (e.key === "Delete") {
      // いきなり削除しない。「…」メニューを開くだけ。
      e.preventDefault();
      openMenu();
    }
  };

  return (
    <div
      className="tsumiki-list-row"
      role="button"
      tabIndex={0}
      onClick={onToggleSelect}
      onKeyDown={onKeyDown}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        position: "relative",
        display: "flex",
        alignItems: "center",
        gap: 14,
        minHeight: 56,
        padding: "14px 18px",
        boxSizing: "border-box",
        cursor: "pointer",
        background: selected
          ? "rgba(0,0,0,0.05)"
          : hover
            ? "rgba(0,0,0,0.03)"
            : "transparent",
        borderBottom: isLast ? "none" : "1px solid rgba(0,0,0,0.06)",
      }}
    >
      <div
        style={{
          width: 3,
          alignSelf: "stretch",
          borderRadius: 4,
          background: STATE_BAR_COLORS[task.state],
          flexShrink: 0,
        }}
        aria-hidden="true"
      />
      <button
        type="button"
        onClick={onIconClick}
        aria-label={isDone ? "完了を取り消す" : "完了にする"}
        style={{
          display: "flex",
          flexShrink: 0,
          padding: 0,
          border: "none",
          background: "transparent",
          cursor: "pointer",
          borderRadius: 9999,
        }}
      >
        <StateIcon done={isDone} />
      </button>
      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          gap: 4,
        }}
      >
        <span
          style={{
            fontSize: 15,
            fontWeight: 400,
            lineHeight: 1.47,
            color: isDone ? "#615d59" : "rgba(0,0,0,0.95)",
            textDecoration: isDone ? "line-through" : "none",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {task.title}
        </span>
        <span
          style={{
            fontSize: 13,
            fontWeight: 400,
            lineHeight: 1.43,
            color: "#615d59",
          }}
        >
          {formatRelativeTime(task.updated_at)} · {STATE_LABELS[task.state]}
        </span>
      </div>
      <button
        ref={menuButtonRef}
        type="button"
        onClick={onMenuButtonClick}
        aria-label="操作メニュー"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        style={{
          position: "absolute",
          right: 12,
          top: "50%",
          transform: "translateY(-50%)",
          width: 28,
          height: 28,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          border: "none",
          borderRadius: 4,
          background: hover || menuOpen ? "rgba(0,0,0,0.05)" : "transparent",
          cursor: "pointer",
          opacity: hover || menuOpen ? 1 : 0,
          pointerEvents: hover || menuOpen ? "auto" : "none",
          color: "#615d59",
          fontSize: 18,
          fontWeight: 700,
          lineHeight: 1,
        }}
      >
        …
      </button>
      {menuOpen && menuButtonRef.current && (
        <TaskMenu
          anchorRect={menuButtonRef.current.getBoundingClientRect()}
          destinations={destinations}
          onSelectState={onChangeState}
          onDelete={onDelete}
          onClose={closeMenu}
        />
      )}
    </div>
  );
}

function StateIcon({ done }: { done: boolean }) {
  if (done) {
    return (
      <svg
        width="18"
        height="18"
        viewBox="0 0 18 18"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
        style={{ flexShrink: 0 }}
      >
        <circle cx="9" cy="9" r="8" stroke="#1aae39" strokeWidth="2" />
        <path
          d="M5.5 9.3L7.8 11.6L12.5 6.6"
          stroke="#1aae39"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 18 18"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      style={{ flexShrink: 0 }}
    >
      <circle cx="9" cy="9" r="8" stroke="#a39e98" strokeWidth="1.6" />
    </svg>
  );
}

const POPOVER_WIDTH = 180;

// 行の「…」から開くポップオーバー。document.body への portal で描画する
// （カードの overflow:hidden や行のスクロール領域に切り取られないため）。
function TaskMenu({
  anchorRect,
  destinations,
  onSelectState,
  onDelete,
  onClose,
}: {
  anchorRect: DOMRect;
  destinations: TaskState[];
  onSelectState: (dest: TaskState) => void;
  onDelete: () => void;
  onClose: () => void;
}) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDocMouseDown = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    const onDocKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDocMouseDown);
    document.addEventListener("keydown", onDocKeyDown);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      document.removeEventListener("keydown", onDocKeyDown);
    };
  }, [onClose]);

  const itemStyle: CSSProperties = {
    display: "block",
    width: "100%",
    textAlign: "left",
    padding: "8px 12px",
    border: "none",
    background: "transparent",
    cursor: "pointer",
    fontFamily: "inherit",
    fontFeatureSettings: "inherit",
    fontSize: 13,
    fontWeight: 600,
    lineHeight: 1.33,
    color: "rgba(0,0,0,0.95)",
  };

  return createPortal(
    <div
      ref={popoverRef}
      className="tsumiki-popover"
      role="menu"
      style={{
        position: "fixed",
        top: anchorRect.bottom + 4,
        left: Math.max(8, anchorRect.right - POPOVER_WIDTH),
        width: POPOVER_WIDTH,
        background: "#ffffff",
        border: "1px solid rgba(0,0,0,0.1)",
        borderRadius: 8,
        boxShadow: SOFT_CARD_SHADOW,
        overflow: "hidden",
        fontFamily: FONT_STACK,
        fontFeatureSettings: '"lnum"',
        zIndex: 1000,
        padding: "4px 0",
      }}
    >
      {destinations.map((dest) => (
        <MenuItem
          key={dest}
          label={`${STATE_LABELS[dest]}へ`}
          itemStyle={itemStyle}
          onClick={() => {
            onSelectState(dest);
            onClose();
          }}
        />
      ))}
      {destinations.length > 0 && (
        <div
          style={{ height: 1, background: "rgba(0,0,0,0.06)", margin: "4px 0" }}
          aria-hidden="true"
        />
      )}
      <MenuItem
        label={confirmingDelete ? "本当に削除" : "削除"}
        itemStyle={{
          ...itemStyle,
          color: confirmingDelete ? "#a8620f" : "rgba(0,0,0,0.95)",
        }}
        onClick={() => {
          if (confirmingDelete) {
            onDelete();
            onClose();
          } else {
            setConfirmingDelete(true);
          }
        }}
      />
    </div>,
    document.body,
  );
}

function MenuItem({
  label,
  itemStyle,
  onClick,
}: {
  label: string;
  itemStyle: CSSProperties;
  onClick: () => void;
}) {
  const [hover, setHover] = useState(false);
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ ...itemStyle, background: hover ? "rgba(0,0,0,0.03)" : "transparent" }}
    >
      {label}
    </button>
  );
}
