//! ファイルへのログ出力。
//!
//! `main.rs` の `windows_subsystem = "windows"` により、リリースビルドには
//! コンソールが無い。`tracing_subscriber::fmt::init()` の既定の書き込み先
//! （stdout）は宛先を失い、障害が起きてもログが一切残らなくなる（T19 の
//! 実機確認で判明）。ここでは Tauri の `app_log_dir()` （自前でパスを組み立てない）
//! 配下に必ずファイルとして残す。開発時（`debug_assertions`）は、これまで
//! `pnpm tauri dev` のターミナルで見えていたコンソール出力も維持する。

use tauri::Manager;
use tracing_subscriber::prelude::*;
use tracing_subscriber::EnvFilter;

/// 既定のログレベル。`tracing_subscriber::fmt::init()` は内部で
/// `EnvFilter::from_default_env()` を組み込んでおり、`RUST_LOG` 未設定時は
/// 控えめなレベルに落ちる。`registry()` に組み替えると自動では付かないため、
/// ここで明示的に付け直す。既定は自分のアプリのログが読める程度の "info" とし、
/// `RUST_LOG` で上書きできるようにする（デバッグ時に `RUST_LOG=debug` で深く見る）。
/// これを付けないと tauri/wry/hyper/reqwest 等の依存クレートの DEBUG/TRACE まで
/// 素通しになり、常駐アプリでは1日分のログファイルがすぐ肥大する。
fn env_filter() -> EnvFilter {
    EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"))
}

/// 呼び出し元（`run()` の `setup` フック）は返された `WorkerGuard` を
/// アプリの生存期間ずっと保持すること（`app.manage()` に渡すなど）。
/// non-blocking writer はログ行を一旦バッファしてバックグラウンドスレッドへ
/// 渡すため、guard が drop されるとバッファに残った行が書き出されずに消える。
///
/// 初期化そのものが失敗した場合（`app_log_dir()` の解決失敗、ディスクフル、
/// 権限不足など）は `Err` を返す。呼び出し側はこれでアプリの起動を止めない方針
/// （ログは道具であってアプリの目的ではない。タスクを捕捉できることの方が優先）。
pub fn init(app: &tauri::App) -> anyhow::Result<tracing_appender::non_blocking::WorkerGuard> {
    let log_dir = app.path().app_log_dir()?;
    std::fs::create_dir_all(&log_dir)?;

    // 日次ローテーション + 直近14日分だけ保持。常駐アプリのログ量は多くなく、
    // サイズでの打ち切りより「何日分残っているか」の方が扱いやすいため日次を選んだ。
    // 14日という日数に強い根拠はなく、多すぎず少なすぎない値としての目安。
    let file_appender = tracing_appender::rolling::Builder::new()
        .rotation(tracing_appender::rolling::Rotation::DAILY)
        .filename_prefix("tsumiki")
        .filename_suffix("log")
        .max_log_files(14)
        .build(&log_dir)?;
    let (non_blocking, guard) = tracing_appender::non_blocking(file_appender);

    let file_layer = tracing_subscriber::fmt::layer()
        .with_writer(non_blocking)
        // ログファイルに ANSI エスケープシーケンスの色付けを残さない。
        .with_ansi(false)
        .with_filter(env_filter());

    #[cfg(debug_assertions)]
    tracing_subscriber::registry()
        .with(file_layer)
        // 開発時はこれまで通りコンソールにも出す（`pnpm tauri dev` の見え方を壊さない）。
        .with(tracing_subscriber::fmt::layer().with_filter(env_filter()))
        .init();

    #[cfg(not(debug_assertions))]
    tracing_subscriber::registry().with(file_layer).init();

    // 「ログがどこにあるか分からない」が次の詰まりどころにならないよう、
    // 出力先そのものをログの1行目に書く。
    tracing::info!("ログ出力先: {}", log_dir.display());

    Ok(guard)
}
