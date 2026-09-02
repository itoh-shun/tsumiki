import Capture from "./Capture";
import List from "./List";

// 捕捉小窓は同じフロントエンドを別ルートで出す（`?capture=1`）。
// hotkey.rs 側で WebviewUrl::App("index.html?capture=1") を使って開く。
const isCapture = new URLSearchParams(window.location.search).has("capture");

export default function App() {
  if (isCapture) {
    return <Capture />;
  }
  return <List />;
}
