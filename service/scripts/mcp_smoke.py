"""tsumiki-mcp の疎通確認スクリプト。

`claude mcp add` のように利用者の MCP 設定を書き換えるコマンドは一切実行しない。
代わりに tsumiki-service と tsumiki-mcp を自前の一時ディレクトリでサブプロセス起動し、
MCP の JSON-RPC ハンドシェイク (initialize -> tools/list -> tools/call) を素通しで確認する。

実行:
    uv run python scripts/mcp_smoke.py

前提:
    このスクリプトが tsumiki-service / tsumiki-mcp の起動・停止まで面倒を見るため、
    事前にサービスを起動しておく必要はない。実データ (~/.tsumiki) には一切触れない。
"""

import asyncio
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVICE_ROOT = Path(__file__).resolve().parent.parent

EXPECTED_TOOLS = {
    "add_task",
    "list_tasks",
    "get_task",
    "update_task",
    "complete_task",
    "move_state",
}


def _port_in_use(base_url: str) -> bool:
    """接続できれば(HTTPとして妥当な応答でなくても)使用中とみなす。smoke.sh と同じ規律。"""
    try:
        httpx.get(f"{base_url}/health", timeout=1.0)
        return True
    except httpx.HTTPError:
        return False


def _wait_for_health(base_url: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{base_url}/health", timeout=1.0)
            if resp.status_code == 200:
                return
        except httpx.HTTPError as e:
            last_error = e
        time.sleep(0.3)
    raise RuntimeError(f"tsumiki-service が {timeout}秒以内に起動しませんでした: {last_error}")


def _mcp_server_command() -> list[str]:
    """venv にインストールされた tsumiki-mcp スクリプトを直接叩く。無ければ -m 実行にフォールバック。"""
    bin_path = Path(sys.executable).parent / "tsumiki-mcp"
    if bin_path.exists():
        return [str(bin_path)]
    return [sys.executable, "-m", "app.mcp_server"]


async def _run_mcp_checks(env: dict) -> None:
    params = StdioServerParameters(
        command=_mcp_server_command()[0],
        args=_mcp_server_command()[1:],
        env=env,
        cwd=str(SERVICE_ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_result = await session.list_tools()
            tool_names = {t.name for t in tools_result.tools}
            missing = EXPECTED_TOOLS - tool_names
            if missing:
                raise RuntimeError(f"tools/list に不足があります: {missing} (got={tool_names})")
            for tool in tools_result.tools:
                if tool.name in EXPECTED_TOOLS and not tool.description:
                    raise RuntimeError(f"tool '{tool.name}' に description がありません")
            print(f"tools/list OK: {sorted(tool_names)}")

            call_result = await session.call_tool(
                "add_task", {"title": "MCPスモークテストのタスク"}
            )
            if call_result.is_error:
                raise RuntimeError(f"tools/call(add_task) がエラーを返しました: {call_result.content}")
            print(f"tools/call(add_task) OK: {call_result.content}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="tsumiki-mcp-smoke-") as tmp:
        tmp_path = Path(tmp)
        port = "7339"
        host = "127.0.0.1"

        env = os.environ.copy()
        env["TSUMIKI_DB"] = str(tmp_path / "tsumiki.db")
        env["TSUMIKI_BACKUP_DIR"] = str(tmp_path / "backups")
        env["TSUMIKI_LOG_DIR"] = str(tmp_path / "logs")
        env["TSUMIKI_HOST"] = host
        env["TSUMIKI_PORT"] = port

        base_url = f"http://{host}:{port}"
        if _port_in_use(base_url):
            # smoke.sh と同じ規律: 他人のプロセスは殺さず、使わずに終了する
            raise SystemExit(f"ポート {port} が既に使われています。他のプロセスを停止してから再実行してください")

        service_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                host,
                "--port",
                port,
            ],
            env=env,
            cwd=str(SERVICE_ROOT),
        )
        try:
            _wait_for_health(base_url)
            asyncio.run(_run_mcp_checks(env))
        finally:
            service_proc.terminate()
            try:
                service_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                service_proc.kill()
                service_proc.wait(timeout=5)

    print("mcp_smoke: OK")


if __name__ == "__main__":
    main()
