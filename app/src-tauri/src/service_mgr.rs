//! WSL2 側 tsumiki-service（FastAPI + SQLite）のライフサイクル管理。
//!
//! 大原則: 「利用者が別途手動で起動している常駐サービスを、私たちが黙って殺さない」。
//! これは `scripts/smoke.sh` が本番ポートで既に何かが動いていたら何もせず
//! exit 1 で退く方針と同じ安全原則を、Windows 側から見た形にしたもの。

use anyhow::{anyhow, Context, Result};
use std::process::Stdio;
use std::time::Duration;
use tokio::process::{Child, Command};
use tokio::time::sleep;

#[derive(Debug, Clone)]
pub struct ServiceConfig {
    pub wsl_distro: String,
    pub service_cmd: String,
    pub health_url: String,
    pub startup_timeout: Duration,
}

impl Default for ServiceConfig {
    fn default() -> Self {
        Self {
            wsl_distro: std::env::var("TSUMIKI_WSL_DISTRO").unwrap_or_else(|_| "Ubuntu".into()),
            service_cmd: std::env::var("TSUMIKI_SERVICE_CMD").unwrap_or_else(|_| {
                "uv --directory /home/itoshun/works/tsumiki/service run tsumiki-service".into()
            }),
            health_url: std::env::var("TSUMIKI_HEALTH_URL")
                .unwrap_or_else(|_| "http://127.0.0.1:7331/health".into()),
            startup_timeout: Duration::from_secs(30),
        }
    }
}

pub struct ServiceHandle {
    // Some: 自分で spawn した子プロセス。None: 既に起動していたものを再利用しただけ。
    child: Option<Child>,
}

impl ServiceHandle {
    /// health を先に叩き、既に起動していればそれを再利用する（自分では spawn しない）。
    /// 起動していなければ wsl.exe 経由で spawn し、healthy になるまでポーリングする。
    pub async fn ensure_running(cfg: &ServiceConfig) -> Result<Self> {
        if ping_health(&cfg.health_url).await.is_ok() {
            tracing::info!("tsumiki-service already running, reusing");
            return Ok(Self { child: None });
        }
        let child = spawn_service(cfg).await?;
        wait_until_healthy(cfg).await?;
        Ok(Self { child: Some(child) })
    }

    /// 自分で spawn したプロセスだけを止める。ensure_running() が既存サービスを
    /// 再利用した場合（child が None）は何もしない — 他人のプロセスを殺さない。
    pub async fn stop(mut self) -> Result<()> {
        if let Some(mut c) = self.child.take() {
            let _ = c.kill().await;
        }
        Ok(())
    }
}

async fn spawn_service(cfg: &ServiceConfig) -> Result<Child> {
    // service_cmd は "uv --directory ... run tsumiki-service" のような複数語のシェル
    // コマンド行。wsl.exe にそのまま1トークンとして渡すと空白ごと literal に exec
    // されて失敗するため、`bash -lc` を介して解釈させる。ログインシェルにするのは
    // PATH（uv の install 先が .bashrc/.profile 経由でしか通っていない場合がある）を
    // 確実に通すため。mimicry の service_mgr.rs（単一の実行可能ファイルパスが既定値）
    // からの意図的な差分。
    let child = Command::new("wsl.exe")
        .args(["-d", &cfg.wsl_distro, "--", "bash", "-lc", &cfg.service_cmd])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .stdin(Stdio::null())
        .spawn()
        .context("failed to spawn wsl.exe for tsumiki-service")?;
    Ok(child)
}

async fn wait_until_healthy(cfg: &ServiceConfig) -> Result<()> {
    let start = std::time::Instant::now();
    while start.elapsed() < cfg.startup_timeout {
        if ping_health(&cfg.health_url).await.is_ok() {
            return Ok(());
        }
        sleep(Duration::from_millis(500)).await;
    }
    Err(anyhow!("service did not become healthy in time"))
}

async fn ping_health(url: &str) -> Result<()> {
    let resp = reqwest::Client::new()
        .get(url)
        .timeout(Duration::from_secs(2))
        .send()
        .await?;
    if resp.status().is_success() {
        Ok(())
    } else {
        Err(anyhow!("non-200 from health"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_config_uses_env_overrides() {
        // std::env::set_var/remove_var は近年の rustc で unsafe fn 化されている
        // （マルチスレッド環境での安全性のため）。プロセスグローバルな状態を書き
        // 換える点は変わらないので、このテストを並列実行する他のテストと衝突させ
        // ないよう注意すること（このモジュールには他に環境変数を触るテストは無い）。
        unsafe {
            std::env::set_var("TSUMIKI_WSL_DISTRO", "Foo");
        }
        let cfg = ServiceConfig::default();
        assert_eq!(cfg.wsl_distro, "Foo");
        unsafe {
            std::env::remove_var("TSUMIKI_WSL_DISTRO");
        }
    }

    #[tokio::test]
    async fn ping_to_nonexistent_url_fails() {
        // spawn_service / ensure_running には触れない: 実行環境で wsl.exe を叩いて
        // 実サービスを起動してしまうと、A3 相当の「意図せず本番ポートに干渉する」
        // 事故になる。ここでは ping_health 単体の失敗系だけを検証する。
        let r = ping_health("http://127.0.0.1:1/health").await;
        assert!(r.is_err());
    }
}
