import { useCallback, useEffect, useRef, useState } from "react";
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
// 「タスク行（Task Row）」）。T17: 読んで見せるところまで。行クリックによる
// 状態変更・完了・削除は T18。

const CONNECTION_ERROR_MESSAGE =
  "サービスに繋がりません。tsumiki-service が起動しているか確認してください。";
const EMPTY_MESSAGE = "まだ何もありません。";

interface Task {
  id: number;
  title: string;
  state: TaskState;
  updated_at: string;
}

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

export default function List() {
  const [selectedState, setSelectedState] = useState<TaskState | null>(null);
  const [rows, setRows] = useState<Task[]>([]);
  const [counts, setCounts] = useState<Record<TaskState, number> | null>(null);
  const [connectionError, setConnectionError] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [selectedRowId, setSelectedRowId] = useState<number | null>(null);
  const [connectionTarget, setConnectionTarget] = useState<string | null>(null);

  // list-opened はフォーカスの出入りなどで短時間に複数回飛ぶことがあり得る。
  // 古い応答が新しい応答より後に届いて上書きしないよう、直近の呼び出しだけを
  // 反映するトークンで守る（Capture.tsx の openTokenRef と同じ考え方）。
  const refreshTokenRef = useRef(0);
  // list-opened イベントのハンドラは購読時点の selectedState を古いまま
  // 閉じ込めてしまう（stale closure）ため、常に最新値を ref で持つ。
  const selectedStateRef = useRef<TaskState | null>(null);

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
      */}
      <style>{`
        .tsumiki-list-card button:focus-visible,
        .tsumiki-list-row:focus-visible {
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
                  onToggleSelect={() => toggleRowSelection(task.id)}
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
  onToggleSelect,
}: {
  task: Task;
  isLast: boolean;
  selected: boolean;
  onToggleSelect: () => void;
}) {
  const [hover, setHover] = useState(false);
  const isDone = task.state === "done";

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    // 行はまだクリックしても状態変更などは起きない（T18 で実装）。
    // 見た目上の選択トグルだけはキーボードからも到達できるようにしておく。
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    onToggleSelect();
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
      <StateIcon done={isDone} />
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
