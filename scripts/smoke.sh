#!/usr/bin/env bash
# tsumiki の WSL2 側スモークテスト。
#
# 一時ディレクトリに DB/バックアップ/ログを逃がし、実データ (~/.tsumiki) には一切触れない。
# サービス起動 → CLI での一連の操作 → バックアップ生成確認 → サービス停止 →
# 停止後の CLI エラー挙動確認、までを一通り流す。
#
# 使い方: bash scripts/smoke.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_DIR="$REPO_ROOT/service"

# 既定の 7331 は本番相当の常駐サービスが使う可能性があるポート。
# smoke.sh 専用の別ポートを使うことで、本番サービスと衝突しても本番の DB に
# 書き込んでしまう経路を構造的に無くす(A3)。7339 は mcp_smoke.py が使うので避ける。
HOST="127.0.0.1"
PORT="7338"
BASE_URL="http://${HOST}:${PORT}"

SERVICE_PID=""
TMP_DIR=""

log() {
    echo "==> $1"
}

fail() {
    echo "FAIL: $1" >&2
    exit 1
}

cleanup() {
    local exit_code=$?
    if [ -n "$SERVICE_PID" ] && kill -0 "$SERVICE_PID" 2>/dev/null; then
        log "後片付け: サービス (PGID $SERVICE_PID) を停止します"
        kill -TERM -- "-$SERVICE_PID" 2>/dev/null || kill -TERM "$SERVICE_PID" 2>/dev/null || true
        for _ in $(seq 1 20); do
            kill -0 "$SERVICE_PID" 2>/dev/null || break
            sleep 0.2
        done
        kill -KILL -- "-$SERVICE_PID" 2>/dev/null || true
    fi
    if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
        log "後片付け: 一時ディレクトリ $TMP_DIR を削除します"
        rm -rf "$TMP_DIR"
    fi
    exit "$exit_code"
}
trap cleanup EXIT
# INT/TERM で終了したときも非ゼロで終わるようにしてから EXIT トラップ (cleanup) に渡す。
# そのまま cleanup を INT/TERM にも直接 trap すると、シグナル受信時点で $? に残っている
# 直前コマンドの終了コード(たまたま0のことがある)がそのまま使われてしまう。
trap 'exit 130' INT
trap 'exit 143' TERM

# --- ポートが既に使われていないか確認する -----------------------------------
# 接続できれば(HTTPとして妥当な応答でなくても)使用中とみなし、他人のプロセスは殺さず終了する。
port_in_use() {
    curl -s -o /dev/null --connect-timeout 1 -m 2 "$BASE_URL/health"
}

log "ポート $PORT が既に使われていないか確認します"
if port_in_use; then
    echo "既に起動中です" >&2
    exit 1
fi

# --- 一時ディレクトリへ実データを逃がす ---------------------------------------
TMP_DIR="$(mktemp -d -t tsumiki-smoke-XXXXXX)"
export TSUMIKI_DB="$TMP_DIR/tsumiki.db"
export TSUMIKI_BACKUP_DIR="$TMP_DIR/backups"
export TSUMIKI_LOG_DIR="$TMP_DIR/logs"
export TSUMIKI_HOST="$HOST"
export TSUMIKI_PORT="$PORT"
log "一時ディレクトリを準備しました: $TMP_DIR (port=$PORT)"

run_cli() {
    (cd "$SERVICE_DIR" && uv run tsumiki "$@")
}

# --- サービスを起動する -------------------------------------------------------
log "tsumiki-service を起動します"
setsid uv run --project "$SERVICE_DIR" tsumiki-service >"$TMP_DIR/service.log" 2>&1 &
SERVICE_PID=$!

log "/health が 200 を返すまで待ちます"
deadline=$((SECONDS + 20))
health_ok=0
while [ "$SECONDS" -lt "$deadline" ]; do
    code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 1 -m 2 "$BASE_URL/health" 2>/dev/null || echo "000")"
    if [ "$code" = "200" ]; then
        health_ok=1
        break
    fi
    sleep 0.3
done
if [ "$health_ok" -ne 1 ]; then
    cat "$TMP_DIR/service.log" >&2 || true
    fail "tsumiki-service が制限時間内に起動しませんでした"
fi
log "OK: /health が 200 を返しました"

# --- タスクを2件登録する -------------------------------------------------------
log "タスクを2件登録します"
add1_out="$(run_cli add "スモークテストタスク1")" || fail "1件目のタスク登録に失敗しました"
echo "$add1_out"
task1_id="$(echo "$add1_out" | grep -oE '^#[0-9]+' | tr -d '#')"
[ -n "$task1_id" ] || fail "1件目のタスク id を取得できませんでした: $add1_out"

add2_out="$(run_cli add "スモークテストタスク2" --state next)" || fail "2件目のタスク登録に失敗しました"
echo "$add2_out"
task2_id="$(echo "$add2_out" | grep -oE '^#[0-9]+' | tr -d '#')"
[ -n "$task2_id" ] || fail "2件目のタスク id を取得できませんでした: $add2_out"

# --- ls に2件出ることを確認する ------------------------------------------------
log "tsumiki ls に2件出ることを確認します"
ls_out="$(run_cli ls)" || fail "tsumiki ls に失敗しました"
echo "$ls_out"
count="$(echo "$ls_out" | grep -c '^#')"
[ "$count" -eq 2 ] || fail "タスクが2件のはずが $count 件でした"
log "OK: 2件確認"

# --- 状態を移す ---------------------------------------------------------------
log "タスク #$task2_id を待ちへ移します"
run_cli mv "$task2_id" waiting || fail "tsumiki mv に失敗しました"

log "タスク #$task1_id を完了にします"
run_cli done "$task1_id" || fail "tsumiki done に失敗しました"

# --- 状態が反映されていることを確認する ----------------------------------------
log "tsumiki ls で状態が反映されていることを確認します"
ls_out2="$(run_cli ls)" || fail "tsumiki ls に失敗しました"
echo "$ls_out2"
echo "$ls_out2" | grep -q "^#${task1_id} \[完了\]" || fail "タスク #$task1_id が完了として表示されていません"
echo "$ls_out2" | grep -q "^#${task2_id} \[待ち\]" || fail "タスク #$task2_id が待ちとして表示されていません"
log "OK: 状態反映を確認"

# --- バックアップファイルが1件できていることを確認する ---------------------------
log "バックアップファイルが1件できていることを確認します"
backup_count="$(find "$TSUMIKI_BACKUP_DIR" -maxdepth 1 -name '*.db' 2>/dev/null | wc -l | tr -d ' ')"
[ "$backup_count" -eq 1 ] || fail "バックアップファイルが1件のはずが $backup_count 件でした"
log "OK: バックアップ1件確認"

# --- サービスを停止する -------------------------------------------------------
log "サービスを停止します"
kill -TERM -- "-$SERVICE_PID" 2>/dev/null || kill -TERM "$SERVICE_PID" 2>/dev/null || true
stopped=0
for _ in $(seq 1 20); do
    if ! kill -0 "$SERVICE_PID" 2>/dev/null; then
        stopped=1
        break
    fi
    sleep 0.2
done
if [ "$stopped" -ne 1 ]; then
    kill -KILL -- "-$SERVICE_PID" 2>/dev/null || true
fi
SERVICE_PID=""
log "OK: サービス停止確認"

# --- 停止後の tsumiki ls が終了コード1になることを確認する ------------------------
log "サービス停止後、tsumiki ls が終了コード1になることを確認します"
run_cli ls
ls_exit=$?
if [ "$ls_exit" -ne 1 ]; then
    fail "サービス停止後の tsumiki ls の終了コードが1ではありませんでした(実際: $ls_exit)"
fi
log "OK: 終了コード $ls_exit を確認"

log "スモークテストは全て成功しました"
exit 0
