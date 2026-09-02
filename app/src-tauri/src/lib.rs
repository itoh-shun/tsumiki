use tauri::Manager;
use tokio::sync::Mutex as AsyncMutex;

mod service_mgr;
mod tray;

// T14: トレイ常駐（表示/一時停止/終了）と、閉じるボタンでは終了しない挙動を追加。
// ホットキー本体（T15）と入力ダイアログ（T16）はまだ実装しない。
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
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .manage(tray::TrayState::default())
        .manage(AsyncMutex::new(Option::<service_mgr::ServiceHandle>::None))
        .setup(|app| {
            // 起動時の非表示は tauri.conf.json の visible: false に一本化。
            // ここで重ねて hide() すると一瞬表示されてから消えることがあるため。
            tray::build_tray(app.handle())?;

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
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
