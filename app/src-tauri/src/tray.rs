//! トレイ常駐まわり。メニューは3項目（表示 / 一時停止 / 終了）。
//!
//! 「一時停止」は今のところ状態を保持するだけ（実際にホットキーを無効化する
//! のは T15 側の役割）。`TrayState` は `AppHandle` の managed state として
//! 登録し、T15 のホットキーハンドラから `app.state::<TrayState>()` で読める
//! ようにしてある。

use std::sync::atomic::{AtomicBool, Ordering};

use tauri::menu::{CheckMenuItem, CheckMenuItemBuilder, MenuBuilder, MenuItemBuilder};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager};

pub struct TrayState {
    pub paused: AtomicBool,
}

impl Default for TrayState {
    fn default() -> Self {
        Self {
            paused: AtomicBool::new(false),
        }
    }
}

pub fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let show_item = MenuItemBuilder::with_id("show", "表示").build(app)?;
    let pause_item: CheckMenuItem<tauri::Wry> = CheckMenuItemBuilder::with_id("pause", "一時停止")
        .checked(false)
        .build(app)?;
    let quit_item = MenuItemBuilder::with_id("quit", "終了").build(app)?;

    let menu = MenuBuilder::new(app)
        .item(&show_item)
        .item(&pause_item)
        .item(&quit_item)
        .build()?;

    let pause_item_for_event = pause_item.clone();

    let icon = app
        .default_window_icon()
        .cloned()
        .expect("tauri.conf.json の bundle.icon にアイコンが設定されている前提");

    TrayIconBuilder::new()
        .icon(icon)
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(move |app, event| match event.id().as_ref() {
            "show" => show_and_focus(app),
            "pause" => {
                let checked = pause_item_for_event.is_checked().unwrap_or(false);
                app.state::<TrayState>()
                    .paused
                    .store(checked, Ordering::SeqCst);
                tracing::info!("一時停止: {checked}");
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                toggle_main_window(tray.app_handle());
            }
        })
        .build(app)?;

    Ok(())
}

/// メニューの「表示」用: 非表示なら見せてフォーカスする（トグルではない）。
fn show_and_focus(app: &AppHandle) {
    tracing::info!("show_and_focus 呼び出された");
    if let Some(w) = app.get_webview_window("main") {
        match w.show() {
            Ok(()) => tracing::info!("show_and_focus: show() 成功"),
            Err(e) => tracing::error!("show_and_focus: show() 失敗: {e}"),
        }
        match w.set_focus() {
            Ok(()) => tracing::info!("show_and_focus: set_focus() 成功"),
            Err(e) => tracing::error!("show_and_focus: set_focus() 失敗: {e}"),
        }
        notify_list_opened(&w);
    } else {
        tracing::error!("show_and_focus: main ウィンドウが見つからない");
    }
}

/// トレイアイコン左クリック用: 表示中なら隠す、隠れているなら見せてフォーカスする。
pub fn toggle_main_window(app: &AppHandle) {
    tracing::info!("toggle_main_window 呼び出された");
    if let Some(w) = app.get_webview_window("main") {
        let visible = w.is_visible().unwrap_or(false);
        tracing::info!("toggle_main_window: is_visible()={visible}");
        if visible {
            match w.hide() {
                Ok(()) => tracing::info!("toggle_main_window: hide() 成功"),
                Err(e) => tracing::error!("toggle_main_window: hide() 失敗: {e}"),
            }
        } else {
            match w.show() {
                Ok(()) => tracing::info!("toggle_main_window: show() 成功"),
                Err(e) => tracing::error!("toggle_main_window: show() 失敗: {e}"),
            }
            let _ = w.set_focus();
            notify_list_opened(&w);
        }
    } else {
        tracing::error!("toggle_main_window: main ウィンドウが見つからない");
    }
}

/// 一覧ウィンドウは show()/hide() を繰り返すだけで React コンポーネントは
/// マウントされ直されない（捕捉小窓の hotkey.rs::notify_opened と同じ理由）。
/// 表示されるたびにフロントエンドへ知らせ、最新のタスク一覧を取り直させる。
fn notify_list_opened(w: &tauri::WebviewWindow) {
    if let Err(e) = w.emit("list-opened", ()) {
        tracing::error!("list-opened イベントの発行に失敗: {e}");
    }
}
