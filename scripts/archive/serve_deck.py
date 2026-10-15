# -*- coding: utf-8 -*-
"""判决台本地服务（Python 标准库，零第三方依赖）

存在的理由（2026-10-10）：
  1. file:// 直开判决台时，浏览器禁止加载本地 wasm/模型——摄像头（MediaPipe）必须走
     http 才能用本地资产。本服务把 _vendor/mediapipe/ 全量本地资源递交给页面。
  2. /asr/* 本地语音桥：浏览器采麦克风 PCM POST 过来，本机 sherpa-onnx 模型转写
     （zipformer-ctc-small-zh，60MB），替代走 Google 服务端的 Web Speech API——
     国内网络下后者慢且抽风。模型懒加载：第一次用语音时才载入。

本服务须用带 sherpa_onnx 的解释器运行（D:\\本地模型\\.venv-asr\\pythonw.exe，
「启动判决台.bat」已指向它）；静态文件部分只用标准库，任何 Python 3.8+ 都能跑。

用法：双击「启动判决台.bat」，或
  pythonw scripts\\serve_deck.py            # 静默
  python scripts\\serve_deck.py             # 带日志
"""
import os
import sys
import threading
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # 项目根（D:\\Work\\小红书点赞分析）
PORT = int(os.environ.get("DECK_PORT", "8770"))
DECK = "/00_项目驾驶舱_可视化中心/二审判决台.html"

# ---- 本地 ASR（懒加载；只认"留/删/撤销"三个词，小模型足够）----
ASR_MODEL_DIR = r"D:\本地模型\sherpa-onnx-zipformer-ctc-small-zh-int8-2025-07-16"
ASR_LOCK = threading.Lock()
ASR_REC = None          # sherpa OfflineRecognizer 或 None（未加载）
ASR_ERR = None          # 加载失败原因（给前端看）
ASR_SR = 16000


def asr_load():
    """首次调用时加载模型（约 1-2s，之后常驻内存）。失败不拖垮静态服务。"""
    global ASR_REC, ASR_ERR
    with ASR_LOCK:
        if ASR_REC is not None or ASR_ERR is not None:
            return ASR_REC, ASR_ERR
        try:
            import sherpa_onnx  # noqa
            ASR_REC = sherpa_onnx.OfflineRecognizer.from_zipformer_ctc(
                model=os.path.join(ASR_MODEL_DIR, "model.int8.onnx"),
                tokens=os.path.join(ASR_MODEL_DIR, "tokens.txt"),
                num_threads=2)
        except Exception as e:  # noqa: BLE001
            ASR_ERR = "%s: %s" % (type(e).__name__, e)
        return ASR_REC, ASR_ERR


def asr_transcribe(pcm_bytes):
    """PCM int16 LE 单声道 16k → 文本。返回 (text, err)。"""
    rec, err = asr_load()
    if err:
        return "", err
    try:
        import numpy as np  # noqa
        if len(pcm_bytes) < 2:
            return "", ""
        a = np.frombuffer(pcm_bytes[: len(pcm_bytes) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
        if a.size < ASR_SR // 10:      # 不足 100ms 不当一轮
            return "", ""
        st = rec.create_stream()
        st.accept_waveform(ASR_SR, a)
        rec.decode_stream(st)
        return (st.result.text or "").strip(), ""
    except Exception as e:  # noqa: BLE001
        return "", "%s: %s" % (type(e).__name__, e)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # 项目根（D:\\Work\\小红书点赞分析）
PORT = int(os.environ.get("DECK_PORT", "8770"))
DECK = "/00_项目驾驶舱_可视化中心/二审判决台.html"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",     # 不给这个类型，import() 直接失败
    ".js": "text/javascript; charset=utf-8",
    ".wasm": "application/wasm",
    ".task": "application/octet-stream",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def guess_type(self, path):
        ext = os.path.splitext(path)[1].lower()
        return MIME.get(ext) or super().guess_type(path)

    def end_headers(self):
        # 同源隔离：MediaPipe 的 SIMD/线程 wasm 需要 SharedArrayBuffer 时才不会蔫
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path in ("/", "/index", "/index.html"):
            self.send_response(302)
            self.send_header("Location", quote(DECK))
            self.end_headers()
            return
        if self.path == "/ping":
            body = b'{"ok":true,"service":"deck","root":"' + ROOT.encode("utf-8") + b'"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/asr/ping":
            import json as _json
            body = _json.dumps({"ok": True, "engine": "zipformer-ctc-small-zh",
                                "model_dir": ASR_MODEL_DIR,
                                "loaded": ASR_REC is not None,
                                "err": ASR_ERR}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self):
        if self.path.startswith("/asr/transcribe"):
            n = int(self.headers.get("Content-Length") or 0)
            pcm = self.rfile.read(n) if n > 0 else b""
            text, err = asr_transcribe(pcm)
            import json as _json
            body = _json.dumps({"text": text, "err": err}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args):     # 静默；要日志就注释掉这行
        pass


def main():
    os.chdir(ROOT)
    srv = HTTPServer(("127.0.0.1", PORT), Handler)
    print("判决台本地服务: http://127.0.0.1:%d/  (root=%s)" % (PORT, ROOT))
    print("正在打开浏览器 ...")
    try:
        webbrowser.open("http://127.0.0.1:%d/" % PORT)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
