import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { fetch } from "@tauri-apps/plugin-http";

// tsumiki 捕捉小窓（DESIGN.md §4「捕捉小窓（Capture Window）」「積層バー（Stack Bar）」）。
// T16: Enter で POST /tasks に送信、積層バーは GET /tasks?state=inbox の実件数。

const FONT_STACK =
  '"Inter", "Noto Sans JP", -apple-system, system-ui, "Segoe UI", "Hiragino Sans", "Yu Gothic UI", "Meiryo", Helvetica, Arial';

const DEEP_SHADOW =
  "rgba(0,0,0,0.01) 0px 1px 3px, rgba(0,0,0,0.02) 0px 3px 7px, rgba(0,0,0,0.02) 0px 7px 15px, rgba(0,0,0,0.04) 0px 14px 28px, rgba(0,0,0,0.05) 0px 23px 52px";

const MAX_STACK_BLOCKS = 8;

function hexToRgb(hex: string): [number, number, number] {
  const v = hex.replace("#", "");
  return [
    parseInt(v.substring(0, 2), 16),
    parseInt(v.substring(2, 4), 16),
    parseInt(v.substring(4, 6), 16),
  ];
}

function lerpHex(a: string, b: string, t: number): string {
  const [ar, ag, ab] = hexToRgb(a);
  const [br, bg, bb] = hexToRgb(b);
  const r = Math.round(ar + (br - ar) * t);
  const g = Math.round(ag + (bg - ag) * t);
  const bch = Math.round(ab + (bb - ab) * t);
  return `rgb(${r}, ${g}, ${bch})`;
}

/** i: 下から何段目か（0始まり）。displayedCount: 実際に描く段数（最大8）。 */
function blockColor(i: number, displayedCount: number): string {
  if (i === displayedCount - 1) {
    return "#d98324"; // 最上段のみアクセント塗り
  }
  const nonTopCount = displayedCount - 1;
  if (nonTopCount <= 1) return "#e8e4e0";
  const t = i / (nonTopCount - 1); // 下(0)ほど淡く、上に近いほど #e8e4e0 寄り
  return lerpHex("#f0ece8", "#e8e4e0", t);
}

async function getBaseUrl(): Promise<string> {
  return await invoke<string>("service_base_url");
}

async function fetchInboxCount(base: string): Promise<number> {
  try {
    // 開くたびに最新件数を取り直したいので、GET のブラウザキャッシュに
    // 乗らないよう明示的に無効化する。
    const res = await fetch(`${base}/tasks?state=inbox`, {
      method: "GET",
      cache: "no-store",
    });
    if (!res.ok) return 0;
    const data = (await res.json()) as unknown;
    return Array.isArray(data) ? data.length : 0;
  } catch {
    // 取得に失敗しても小窓の表示自体は止めない。0 件として描く。
    return 0;
  }
}

export default function Capture() {
  const inputRef = useRef<HTMLInputElement>(null);
  const submittingRef = useRef(false);

  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inboxCount, setInboxCount] = useState(0);
  // capture-opened はフォーカスのちらつきなどで短時間に複数回飛ぶことがある。
  // 古い GET の応答が新しい応答より後に届いて上書きしてしまわないよう、
  // 直近の呼び出しだけを反映するトークンで守る。
  const openTokenRef = useRef(0);

  // 小窓は hide()/show() を繰り返すだけで React コンポーネントは
  // マウントされ直されない。「開くたびに」の処理はこの関数にまとめ、
  // 初回マウント（Rust 側の capture-opened が先に飛んで拾えなかった
  // 場合の保険）と capture-opened イベントの両方から呼ぶ。
  const onOpened = useCallback(() => {
    setText("");
    setError(null);
    submittingRef.current = false;
    setSubmitting(false);
    inputRef.current?.focus();
    const token = ++openTokenRef.current;
    void (async () => {
      let count = 0;
      try {
        const base = await getBaseUrl();
        count = await fetchInboxCount(base);
      } catch (e) {
        // service_base_url() 自体が失敗しても 0 件扱いにする
        // （取得失敗は小窓の表示を止めない）。
        console.error("failed to refresh inbox count", e);
      }
      if (openTokenRef.current === token) {
        setInboxCount(count);
      }
    })();
  }, []);

  useEffect(() => {
    onOpened();

    const unlistenPromise = listen("capture-opened", () => onOpened());

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      // 捕捉の速さが最優先。確認ダイアログは挟まない。入力中の文字も確認なしで破棄する。
      void invoke("hide_capture");
    };
    window.addEventListener("keydown", onKeyDown);

    return () => {
      window.removeEventListener("keydown", onKeyDown);
      void unlistenPromise.then((unlisten) => unlisten());
    };
  }, [onOpened]);

  const submit = useCallback(async () => {
    const title = text.trim();
    if (title.length === 0) {
      // 空文字・空白のみは送信しない。閉じるだけでよい。
      await invoke("hide_capture");
      return;
    }
    if (submittingRef.current) return; // 連打対策（state の非同期更新より先に効かせる）
    submittingRef.current = true;
    setSubmitting(true);
    setError(null);

    try {
      const base = await getBaseUrl();
      const res = await fetch(`${base}/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, state: "inbox" }),
      });
      if (!res.ok) {
        throw new Error(`http_error:${res.status}`);
      }
    } catch (e) {
      submittingRef.current = false;
      setSubmitting(false);
      const message = e instanceof Error ? e.message : "";
      if (message.startsWith("http_error:")) {
        setError(
          `送信に失敗しました（サービスがエラーを返しました: ${message.split(":")[1]}）`,
        );
      } else {
        // サービス停止中は黙って捨てない。閉じずに、入力を残したままエラーを出す。
        setError(
          "サービスに繋がりません。tsumiki-service が起動しているか確認してください。",
        );
      }
      return;
    }

    // ここに来た時点でタスクは既に作成済み。積層バーを1段増やす
    // （厳密な再取得は次に開いたときの capture-opened に任せる）。
    setInboxCount((c) => c + 1);

    // 閉じる/空にするのはあくまで後始末なので、hide() 自体が失敗しても
    // 「送信に失敗した」という誤ったエラーは出さない（握りつぶす）。
    setText("");
    submittingRef.current = false;
    setSubmitting(false);
    try {
      await invoke("hide_capture");
    } catch (e) {
      console.error("capture window hide after successful submit failed", e);
    }
  }, [text]);

  const onInputKeyDown = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    void submit();
  };

  const displayedCount = Math.min(inboxCount, MAX_STACK_BLOCKS);
  const overflow = inboxCount - MAX_STACK_BLOCKS;

  return (
    <>
      {/* インライン style では ::placeholder を指定できないためここだけ style タグで */}
      <style>{`.tsumiki-capture-card input::placeholder { color: #a39e98; }`}</style>
      {/*
        ウィンドウ（Rust 側 hotkey.rs、840x216）はカードより一回り大きい。
        Deep Shadow（下75px・上29px・左右52px）がウィンドウの外に描画
        できず切り落とされてしまうのを避けるため、カードの外側に余白を
        持たせてある。この透明なラッパーがウィンドウ全域を占め、カードを
        水平・垂直中央に置く。余白部分は完全に透明（transparent: true の
        ウィンドウ地がそのまま透ける）。
      */}
      <div
        style={{
          width: "100%",
          height: "100%",
          boxSizing: "border-box",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "transparent",
        }}
      >
        <div
          className="tsumiki-capture-card"
          style={{
            width: 720,
            minHeight: 96,
            boxSizing: "border-box",
            display: "flex",
            alignItems: "stretch",
            background: "#ffffff",
            border: "1px solid rgba(0,0,0,0.1)",
            borderRadius: 16,
            boxShadow: DEEP_SHADOW,
            overflow: "hidden",
            fontFamily: FONT_STACK,
            fontFeatureSettings: '"lnum"',
          }}
        >
          {/* 積層バー: 帯の領域は 0 件でも常に残す（レイアウトを動かさないため）。 */}
        <div
          style={{
            width: 48,
            flexShrink: 0,
            background: "#f6f5f4",
            display: "flex",
            flexDirection: "column-reverse",
            alignItems: "center",
            gap: 3,
            paddingBottom: 8,
            overflow: "hidden",
          }}
        >
          {/*
            flexDirection: column-reverse では DOM の最後の要素が視覚的に
            最も上に来る。「+n」は最上段ブロックのさらに上に出したいので、
            ブロックの配列より後ろ（＝DOM順で最後）に置く。絶対配置の
            マジックナンバーは使わない。
          */}
          {Array.from({ length: displayedCount }).map((_, i) => (
            <div
              key={i}
              style={{
                width: 24,
                height: 8,
                borderRadius: 4,
                background: blockColor(i, displayedCount),
                flexShrink: 0,
              }}
            />
          ))}
          {overflow > 0 && (
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                letterSpacing: "0.125px",
                color: "#615d59",
                flexShrink: 0,
              }}
            >
              +{overflow}
            </span>
          )}
        </div>

        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            padding: "0 18px",
            minWidth: 0,
            gap: 4,
          }}
        >
          <input
            ref={inputRef}
            type="text"
            placeholder="何を捕まえますか"
            value={text}
            disabled={submitting}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onInputKeyDown}
            style={{
              width: "100%",
              border: "none",
              outline: "none",
              background: "transparent",
              fontFamily: "inherit",
              fontFeatureSettings: "inherit",
              fontSize: 20,
              fontWeight: 500,
              lineHeight: 1.4,
              letterSpacing: "-0.125px",
              color: "rgba(0,0,0,0.95)",
            }}
          />
          {error && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                fontSize: 13,
                fontWeight: 400,
                lineHeight: 1.43,
                color: "#615d59",
              }}
            >
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
                <path
                  d="M7 4V7.5"
                  stroke="#a8620f"
                  strokeWidth="1.4"
                  strokeLinecap="round"
                />
                <circle cx="7" cy="9.8" r="0.9" fill="#a8620f" />
              </svg>
              <span>{error}</span>
            </div>
          )}
        </div>

        <div
          style={{
            flexShrink: 0,
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "0 18px",
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 400, color: "#615d59" }}>
            Enter
          </span>
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
          >
            <path
              d="M3 8H13M13 8L9 4M13 8L9 12"
              stroke="#a8620f"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        </div>
      </div>
    </>
  );
}
