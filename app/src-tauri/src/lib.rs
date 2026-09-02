use tauri::Manager;
use tauri_plugin_global_shortcut::GlobalShortcutExt;
use tokio::sync::Mutex as AsyncMutex;

mod hotkey;
mod service_mgr;
mod tray;

// T14: トレイ常駐（表示/一時停止/終了）と、閉じるボタンでは終了しない挙動を追加。
// T15: Alt+Shift+Space で捕捉小窓（hotkey.rs）。
// T16: 捕捉小窓の入力を POST /tasks に配線（フロントエンドが service_base_url() を叩く）。

/// フロントエンドが tsumiki-service の base URL を知るためのコマンド。
/// ポートは service_mgr::ServiceConfig（＝ TSUMIKI_HEALTH_URL）と唯一の情報源を
/// 共有する。ここでハードコードしてしまうと、テスト用に TSUMIKI_HEALTH_URL を
/// 差し替えても実際のリクエスト先だけ本番ポートのままになってしまう。
#[tauri::command]
fn service_base_url() -> String {
    let health_url = service_mgr::ServiceConfig::default().health_url;
    health_url
        .strip_suffix("/health")
        .unwrap_or(&health_url)
        .to_string()
}

/// フロントエンドから捕捉小窓を閉じるためのコマンド。JS 側の
/// `getCurrentWindow().hide()` を直接使わずこちらを経由するのは、
/// T14 で Rust 側の `window.hide()` が確実に効くことを検証済みだった
/// ため、その同じ経路に揃える狙い。
#[tauri::command]
fn hide_capture(window: tauri::WebviewWindow) {
    tracing::info!("hide_capture コマンド呼び出し (label={})", window.label());
    match window.hide() {
        Ok(()) => tracing::info!("hide_capture: hide() 成功"),
        Err(e) => tracing::error!("hide_capture: hide() 失敗: {e}"),
    }
}

pub fn run() {
    tracing_subscriber::fmt::init();

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            tray::toggle_main_window(app);
        }))
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec!["--minimized"]),
        ))
        .plugin(tauri_plugin_notification::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _shortcut, event| {
                    hotkey::handle_shortcut(app, event.state());
                })
                .build(),
        )
        .plugin(tauri_plugin_http::init())
        .invoke_handler(tauri::generate_handler![service_base_url, hide_capture])
        .manage(tray::TrayState::default())
        .manage(hotkey::CaptureFocusGuard::default())
        .manage(AsyncMutex::new(Option::<service_mgr::ServiceHandle>::None))
        .setup(|app| {
            // 起動時の非表示は tauri.conf.json の visible: false に一本化。
            // ここで重ねて hide() すると一瞬表示されてから消えることがあるため。
            tray::build_tray(app.handle())?;

            // 他アプリが同じキーを取っている等で登録に失敗しても、アプリ自体は落とさない。
            if let Err(e) = app.global_shortcut().register(hotkey::shortcut()) {
                tracing::error!("グローバルショートカットの登録に失敗: {e}");
            }

            // tsumiki-service の起動導線。既に動いているサービスは
            // service_mgr::ServiceHandle::ensure_running() が再利用するだけで
            // 止めない（既存の安全な挙動はここでは変えていない）。
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                match service_mgr::ServiceHandle::ensure_running(
                    &service_mgr::ServiceConfig::default(),
                )
                .await
                {
                    Ok(h) => {
                        tracing::info!("tsumiki-service ready");
                        let state = handle.state::<AsyncMutex<Option<service_mgr::ServiceHandle>>>();
                        *state.lock().await = Some(h);
                    }
                    Err(e) => tracing::error!("tsumiki-service ensure_running failed: {e}"),
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            // 常駐アプリなので、閉じるボタン＝終了ではなくトレイに戻すだけ。
            if window.label() == "main" {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    tracing::info!("CloseRequested を受け取った、hide に切り替える");
                    api.prevent_close();
                    match window.hide() {
                        Ok(()) => tracing::info!("hide() 成功"),
                        Err(e) => tracing::error!("hide() 失敗: {e}"),
                    }
                }
            }
            // 捕捉小窓はフォーカスを失ったら閉じる（破棄はせず hide のみ）。
            // ただし「一度も本当にフォーカスを得ていない」場合は hide しない
            // （environment 依存でフォーカスが乗らなかっただけの可能性があり、
            // 閉じ損なうより開き損なう方がまし。hotkey::CaptureFocusGuard 参照）。
            if window.label() == hotkey::CAPTURE_LABEL {
                let guard = window.state::<hotkey::CaptureFocusGuard>();
                match event {
                    tauri::WindowEvent::Focused(true) => {
                        tracing::info!("捕捉小窓がフォーカスを得た");
                        guard.mark_focused();
                    }
                    tauri::WindowEvent::Focused(false) => {
                        if guard.should_hide_on_blur() {
                            tracing::info!("捕捉小窓がフォーカスを失った、hide する");
                            let _ = window.hide();
                        } else {
                            tracing::info!(
                                "捕捉小窓が Focused(false) を受けたが、一度もフォーカスを得ていないため hide しない"
                            );
                        }
                    }
                    _ => {}
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
