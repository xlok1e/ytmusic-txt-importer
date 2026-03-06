"""
Entry point for the packaged application (PyInstaller).
Starts the FastAPI server and opens the browser automatically.
"""
import os
import sys
import socket
import threading
import time
import webbrowser

import uvicorn


def find_free_port(preferred: int = 8765) -> int:
    """Return preferred port if free, otherwise find any available port."""
    for port in (preferred, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
        except OSError:
            continue
    raise RuntimeError("Could not find a free port")


def wait_and_open_browser(port: int, delay: float = 1.5) -> None:
    time.sleep(delay)
    webbrowser.open(f"http://127.0.0.1:{port}")


if __name__ == "__main__":
    port = find_free_port()

    browser_thread = threading.Thread(
        target=wait_and_open_browser,
        args=(port,),
        daemon=True,
    )
    browser_thread.start()

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
