"""Frozen-app entry point for the local PicMeasure web workbench."""

from __future__ import annotations

import threading
import webbrowser

import uvicorn


def main() -> None:
    """Start the web server and open the local workbench."""
    threading.Timer(0.8, webbrowser.open, args=("http://127.0.0.1:8765",)).start()
    uvicorn.run("picmeasure.web:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
