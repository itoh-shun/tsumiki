import Capture from "./Capture";

// 捕捉小窓は同じフロントエンドを別ルートで出す（`?capture=1`）。
// hotkey.rs 側で WebviewUrl::App("index.html?capture=1") を使って開く。
const isCapture = new URLSearchParams(window.location.search).has("capture");

// メインウィンドウ側は T16（入力ダイアログ本体を含む一覧UI）まで未実装のプレースホルダー。
export default function App() {
  if (isCapture) {
    return <Capture />;
  }
  return <div>tsumiki</div>;
}
