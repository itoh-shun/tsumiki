//! グローバルホットキー（Alt+Shift+Space）で捕捉小窓を出す。
//!
//! 最重要の落とし穴: グローバルショートカットのハンドラは押下と解放の
//! 両方で発火する。`ShortcutState::Pressed` のときだけ処理しないと、
//! 押した瞬間に開いて離した瞬間に閉じる（＝実質何も出ない）。

use std::sync::atomic::{AtomicBool, Ordering};

use tauri::{
    AppHandle, Emitter, Manager, PhysicalPosition, PhysicalSize, WebviewUrl, WebviewWindowBuilder,
};
use tauri_plugin_global_shortcut::{Code, Modifiers, Shortcut, ShortcutState};

use crate::tray::TrayState;

pub const CAPTURE_LABEL: &str = "capture";

// カード（DESIGN.md §4 の捕捉小窓そのもの）のサイズ。Deep Shadow を
// 描画するための余白ではなく、あくまで見た目上のカードの寸法。
const CARD_WIDTH: f64 = 720.0;
const CARD_MIN_HEIGHT: f64 = 96.0;

// ウィンドウ自体はカードより一回り大きく取る。カードは Capture.tsx 側で
// このウィンドウの中央に置かれ、はみ出した余白は transparent なまま。
// Deep Shadow（下方向は offset 23px + blur 52px = 75px、上方向は
// blur 52px - offset 23px = 29px、左右は blur 52px = 52px）が
// ウィンドウ境界で切り落とされないよう、片側 60px（合計120px）の
// 余白を確保している。
const WINDOW_WIDTH: f64 = CARD_WIDTH + 120.0; // 840.0
const WINDOW_MIN_HEIGHT: f64 = CARD_MIN_HEIGHT + 120.0; // 216.0

/// 捕捉小窓が「一度でも本当にフォーカスを得たか」を覚えておく。
///
/// `WindowEvent::Focused(false)` は、環境によっては新規作成直後の
/// ウィンドウが実際には OS フォーカスを奪えないまま届くことがある
/// （例: 何らかの理由でフォーカスが乗らなかった場合）。時間で無視する
/// （n ms 以内は無視、等）とマシン速度に依存して不安定になるため、
/// 「一度 Focused(true) を観測してからでないと Focused(false) では
/// hide しない」という状態ベースのガードにしてある。
/// フォーカスを取れなかった場合は開いたまま残る
/// （閉じ損なうより開き損なう方がまし）。
#[derive(Default)]
pub struct CaptureFocusGuard {
    focused_once: AtomicBool,
}

impl CaptureFocusGuard {
    pub fn mark_focused(&self) {
        self.focused_once.store(true, Ordering::SeqCst);
    }

    /// フォーカスを失った時に呼ぶ。一度も本当にフォーカスしていなければ
    /// false を返す（＝ hide しない）。
    pub fn should_hide_on_blur(&self) -> bool {
        self.focused_once.swap(false, Ordering::SeqCst)
    }

    fn reset_before_show(&self) {
        self.focused_once.store(false, Ordering::SeqCst);
    }
}

pub fn shortcut() -> Shortcut {
    Shortcut::new(Some(Modifiers::ALT | Modifiers::SHIFT), Code::Space)
}

/// `tauri_plugin_global_shortcut` のハンドラから呼ばれる。
pub fn handle_shortcut(app: &AppHandle, state: ShortcutState) {
    // 離した瞬間の発火はここで捨てる。
    if state != ShortcutState::Pressed {
        return;
    }

    if app.state::<TrayState>().paused.load(Ordering::SeqCst) {
        tracing::info!("一時停止中のため捕捉ホットキーを無視");
        return;
    }

    toggle_capture(app);
}

fn toggle_capture(app: &AppHandle) {
    let guard = app.state::<CaptureFocusGuard>();

    if let Some(w) = app.get_webview_window(CAPTURE_LABEL) {
        let visible = w.is_visible().unwrap_or(false);
        tracing::info!("捕捉小窓トグル: 既存ウィンドウ visible={visible}");
        if visible {
            let _ = w.hide();
        } else {
            guard.reset_before_show();
            position_window(&w);
            let _ = w.show();
            let _ = w.set_focus();
            notify_opened(&w);
        }
        return;
    }

    tracing::info!("捕捉小窓を新規作成する");
    guard.reset_before_show();
    match build_capture_window(app) {
        Ok(w) => {
            position_window(&w);
            let _ = w.show();
            let _ = w.set_focus();
            notify_opened(&w);
        }
        Err(e) => tracing::error!("捕捉小窓の作成に失敗: {e}"),
    }
}

/// 捕捉小窓は show()/hide() を繰り返すだけで React コンポーネントは
/// マウントされ直さない。開くたびに「入力欄を空にする・積層バーの
/// 件数を取り直す・入力にフォーカスする」をフロントエンド側にやらせる
/// ため、専用イベントで明示的に知らせる。
fn notify_opened(w: &tauri::WebviewWindow) {
    if let Err(e) = w.emit("capture-opened", ()) {
        tracing::error!("capture-opened イベントの発行に失敗: {e}");
    }
}

fn build_capture_window(app: &AppHandle) -> tauri::Result<tauri::WebviewWindow> {
    WebviewWindowBuilder::new(
        app,
        CAPTURE_LABEL,
        WebviewUrl::App("index.html?capture=1".into()),
    )
    .title("tsumiki capture")
    .decorations(false)
    .transparent(true)
    .always_on_top(true)
    .skip_taskbar(true)
    .resizable(false)
    .shadow(false)
    .visible(false)
    .inner_size(WINDOW_WIDTH, WINDOW_MIN_HEIGHT)
    .build()
}

/// カードの中心が画面上から1/3の高さ（視線が速く届く位置）に来るように置く。
/// カードは Capture.tsx 側でウィンドウの水平・垂直中央に配置されるので、
/// カードの中心 = ウィンドウの中心。ウィンドウ自体を目標位置に中央寄せすれば
/// カードもそこに来る。
fn position_window(w: &tauri::WebviewWindow) {
    let monitor = match w.current_monitor() {
        Ok(Some(m)) => m,
        _ => return,
    };
    let screen: &PhysicalSize<u32> = monitor.size();
    let win_size = w
        .outer_size()
        .unwrap_or(PhysicalSize::new(WINDOW_WIDTH as u32, WINDOW_MIN_HEIGHT as u32));

    let x = (screen.width as i32 - win_size.width as i32) / 2;
    // 中央（1/2）よりやや上 = 上から1/3の高さにウィンドウ（＝カード）の中心を置く。
    let y = ((screen.height as i32) / 3 - (win_size.height as i32) / 2).max(0);

    let _ = w.set_position(PhysicalPosition::new(x, y));
}
