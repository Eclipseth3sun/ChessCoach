"""ChessCoach desktop entry point: uvicorn in a thread + native WebView2 window.

The server runs in a background thread; when the window closes we explicitly
stop the server and hard-exit so port 8421 is always released (a plain daemon
thread can leave the socket held on Windows).
"""
import os
import threading
import time

import httpx
import uvicorn
import webview

from backend.app import app

PORT = 8421
URL = f"http://127.0.0.1:{PORT}"

server: uvicorn.Server | None = None


def serve():
    global server
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    server.run()


def main():
    t = threading.Thread(target=serve, daemon=True)
    t.start()
    # wait for the server to come up before opening the window
    for _ in range(50):
        try:
            httpx.get(f"{URL}/api/settings", timeout=1)
            break
        except Exception:
            time.sleep(0.1)

    webview.create_window("ChessCoach", URL, width=1440, height=920)
    webview.start()  # blocks until the window is closed

    # Window closed: ask the server to stop gracefully, then force the whole
    # process down so the port is freed even if a thread is slow to unwind.
    if server is not None:
        server.should_exit = True
    t.join(timeout=5)
    os._exit(0)


if __name__ == "__main__":
    main()
