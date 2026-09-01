# tsumiki app（Windows 常駐 UI / Tauri 2）

Tauri 2 + React + TypeScript + Vite。WSL2 側の `service/`（FastAPI + SQLite）を Windows から常駐操作するデスクトップアプリの雛形。

## 結論: ビルドは `C:\dev\tsumiki\app` で行う

**`\\wsl.localhost\Ubuntu\...` の UNC パス上ではビルドが完走しません。** WSL2 側で `service/` を編集する分には問題ありませんが、`app/`（Tauri アプリ）は Windows のローカルディスク（NTFS）にクローンしたコピー上でビルド・検証してください。

```powershell
git clone https://github.com/itoh-shun/tsumiki C:\dev\tsumiki
cd C:\dev\tsumiki\app
pnpm install
pnpm build
cd src-tauri
cargo check
cargo test
```

WSL2 側からは `/mnt/c/dev/tsumiki` でこのコピーを読み書きできます（後述の **git の注意** を参照）。

### PowerShell を使うこと（cmd.exe は使わない）

`cmd.exe` は `\\wsl.localhost\...` のような UNC パスに `cd` できません。WSL2 のパスにアクセスする必要がある操作（このコピー自体には不要ですが、参照用に残す）は必ず PowerShell から行ってください。

## UNC パス上で実際に踏んだ3件の問題

`C:\dev\tsumiki` に切り替える前、`\\wsl.localhost\Ubuntu\home\itoshun\works\tsumiki\app` を直接ビルドしようとして、以下の3件の障害を実際に踏みました。原因はどれも共通していて、**UNC（9P 経由のネットワークパス）が通常の NTFS ローカルディスク前提の低レベル API を満たさない**ことです。

1. **cargo のインクリメンタルコンパイルがセッションディレクトリのロックファイルを作れない**

   ```
   error: incremental compilation: could not create session directory lock file:
   ファンクションが間違っています。 (os error -2147024895)
   ```

   Rust のインクリメンタルコンパイルはセッションディレクトリにロックファイルを作りますが、UNC パスはこのファイルロック機構をサポートしません。`CARGO_INCREMENTAL=0` で回避できますが、恒久策にはしません（後述）。

2. **pnpm のネイティブ copy-on-write がボリューム情報の問い合わせに失敗して abort**

   ```
   thread '<unnamed>' panicked at ...copy_on_write-0.1.3\src\platform\windows.rs:42:54:
   Failed to get destination volume info: Error { code: HRESULT(0x80070002), message: "指定されたファイルが見つかりません。" }
   thread caused non-unwinding panic. aborting.
   ```

   pnpm はパッケージを content-addressable store からリンクする際、ReFS の block cloning などが使えるかボリューム情報を問い合わせます。UNC パスではこの問い合わせ自体が失敗し、本来ならフォールバックすべきところで native コードが panic してプロセスごと落ちます。

3. **`.npmrc` の `package-import-method=copy` で回避を試みたが効かなかった**

   pnpm の公式な回避策（`package-import-method=copy` で native な hardlink/clone を使わず単純コピーにする）を `.npmrc` に設定しましたが、`pnpm config get package-import-method` が `undefined` を返し、設定が読み込まれていないことが分かりました（原因未特定）。同じ panic が再発しました。

この3件目の時点で「個別の問題に個別の回避策」ではなく**構成そのものが間違っている**と判断し、`app/` のビルド場所を Windows ローカルディスク（`C:\dev\tsumiki`）に切り替えました。切り替え後、上記3件は**すべて再発していません**（`.npmrc` は不要になったため削除済み）。

## UNC と NTFS の所要時間比較

UNC 側は3件とも別々の cargo 呼び出し（profile が異なる）で、「1回目/2回目」の関係にはありません。NTFS 側は同一の `cargo check` を連続2回実行した「1回目=フルビルド」「2回目=無変更再実行」です。

| 測定 | 環境 | profile | 所要時間 |
|---|---|---|---|
| `cargo check` 単独実行（`CARGO_INCREMENTAL=0` 付き） | UNC | dev | 6分16秒 |
| `cargo test` 単独実行（`CARGO_INCREMENTAL=0` 付き） | UNC | test | 15分39秒（うちビルドが14分33秒） |
| `cargo check` 1回目（フルビルド） | NTFS | dev | **1分56秒**（116.0秒、インクリメンタル有効のまま） |
| `cargo check` 2回目（無変更再実行） | NTFS | dev | **5.1秒**（インクリメンタルが効いている） |
| `cargo test` 単独実行 | NTFS | test | **2分15秒**（135.3秒、うちビルドが2分11秒） |

NTFS では `CARGO_TARGET_DIR` / `CARGO_INCREMENTAL` の設定は一切不要。デフォルトのままインクリメンタルコンパイルが正常に機能し、UNC 比で `cargo check` は3倍以上、無変更再実行では 1分台 → 5秒程度まで短縮された。UI 実装（T14〜T16）のような試行回数の多いフェーズでは、この差は致命的に効いてくる。

## pnpm のビルドスクリプト承認（UNC とは無関係の別件）

`pnpm install` は UNC 問題を解消した後も、pnpm 11 系の仕様で以下のエラーを出します（これはプラットフォームに関係なく発生する、pnpm の supply-chain セキュリティ機能です）:

```
[ERR_PNPM_IGNORED_BUILDS] Ignored build scripts: esbuild@0.28.2
Run "pnpm approve-builds" to pick which dependencies should be allowed to run scripts.
```

pnpm 11 では `package.json` の `"pnpm"` フィールドはもう読まれず、`pnpm-workspace.yaml` の `allowBuilds` に移っています。`app/pnpm-workspace.yaml` に以下を追加して解決しています:

```yaml
allowBuilds:
  esbuild: true
```

## git の注意: `C:\dev\tsumiki` では Windows 側の git を使うこと

`C:\dev\tsumiki` を **WSL2 側の `git`（`/mnt/c/dev/tsumiki` 経由）で** `git status`/`git diff` すると、全ファイルが変更ありと表示されます。これは実際の内容変更ではなく、Windows の git（`core.autocrlf=true` 相当）でチェックアウトした際に付与された CRLF 改行を、WSL2 側の git（`core.autocrlf=false`）がバイト単位で比較して「全行変更」と判定しているだけです（`git diff` で全行が `-`/`+` ペアになっているのに内容は同一、という形で確認済み）。

**`C:\dev\tsumiki` に対する `git add`/`commit` は、WSL2 の `git` ではなく必ず Windows 側の `git`（PowerShell から実行する `git.exe`）で行ってください。** WSL2 側の git で誤って commit すると、リポジトリ全体（`DESIGN.md` や `service/` の Python コードも含む）の改行コードが CRLF に書き換わってしまいます。
