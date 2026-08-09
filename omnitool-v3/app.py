"""OmniTool – Local File Processing Web App."""

import json
import os
import queue
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, render_template, request, jsonify, Response, send_from_directory
from werkzeug.serving import make_server

from tools import resizer, watermark, audio_converter, video_compressor, pdf_compressor, batch_rename, metadata_stripper, strip_only, password_generator

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
# An AppImage is mounted read-only. Keep user files beside the AppImage while
# retaining the source directory for normal development.
APPIMAGE_PATH = os.environ.get("APPIMAGE")
DATA_DIR = Path(APPIMAGE_PATH).resolve().parent if APPIMAGE_PATH else BASE_DIR
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
TEMP_DIR = DATA_DIR / "temp"
WATERMARK_DIR = DATA_DIR / "watermark"

for d in (INPUT_DIR, OUTPUT_DIR, TEMP_DIR, WATERMARK_DIR):
    d.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)

# Pending job + active worker tracking
_pending_job: dict | None = None
_pending_lock = threading.Lock()
_active_worker: threading.Thread | None = None
_stop_flag = threading.Event()
_server = None
_browser_lock = threading.Lock()
_browser_seen = False
_browser_sessions: dict[str, float] = {}
_browser_empty_since: float | None = None

HEARTBEAT_INTERVAL_SECONDS = 5
HEARTBEAT_TIMEOUT_SECONDS = 45
CLOSE_GRACE_PERIOD_SECONDS = 3


def _send(q: queue.Queue, event: dict):
    """Push an SSE event dict into the queue."""
    q.put(event)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/temp/<path:filename>")
def serve_temp(filename):
    return send_from_directory(str(TEMP_DIR), filename)


@app.route("/api/files")
def list_files():
    """Return a list of files currently in /input."""
    files = []
    for f in sorted(INPUT_DIR.iterdir()):
        if f.is_file():
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "is_watermark": f.name.lower() == "watermark.png",
            })
    return jsonify(files)


@app.route("/api/preview", methods=["POST"])
def preview():
    data = request.get_json(force=True)
    options = data.get("options", {})
    watermark_path = watermark.find_watermark(WATERMARK_DIR)
    if watermark_path is None:
        return jsonify({"ok": False, "error": "There is no watermark image file in /watermark, please put one in that folder."})

    filename = watermark.preview(INPUT_DIR, watermark_path, TEMP_DIR, options)
    if filename:
        return jsonify({"ok": True, "url": f"/temp/{filename}"})
    return jsonify({"ok": False, "error": "No compatible image files found in /input."})


@app.route("/api/password", methods=["POST"])
def password():
    """Generate a password without saving it anywhere."""
    data = request.get_json(force=True)
    try:
        length = int(data.get("length", 16))
        return jsonify({"ok": True, "password": password_generator.generate(length)})
    except (TypeError, ValueError) as error:
        return jsonify({"ok": False, "error": str(error)}), 400


@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    """Record that an OmniTool browser window is still open."""
    global _browser_seen, _browser_empty_since
    data = request.get_json(silent=True) or {}
    session_id = str(data.get("session_id", ""))
    if not session_id:
        return jsonify({"ok": False, "error": "Missing browser session."}), 400

    with _browser_lock:
        _browser_seen = True
        _browser_sessions[session_id] = time.monotonic()
        _browser_empty_since = None
    return "", 204


@app.route("/api/browser-closing", methods=["POST"])
def browser_closing():
    """Stop the server shortly after the last browser window closes."""
    global _browser_empty_since
    data = request.get_json(silent=True) or {}
    session_id = str(data.get("session_id", ""))
    with _browser_lock:
        _browser_sessions.pop(session_id, None)
        if _browser_seen and not _browser_sessions:
            _browser_empty_since = time.monotonic()
    return "", 204


@app.route("/api/process", methods=["POST"])
def process():
    """Store job config for the SSE stream to pick up."""
    global _pending_job
    data = request.get_json(force=True)
    tool_name = data.get("tool")
    options = data.get("options", {})

    TOOL_NAMES = {"resizer", "watermark", "audio", "video", "pdf", "rename", "metadata", "strip_only"}
    if tool_name not in TOOL_NAMES:
        return jsonify({"ok": False, "error": f"Unknown tool: {tool_name}"}), 400

    with _pending_lock:
        _pending_job = {"tool": tool_name, "options": options}

    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def stop():
    """Signal the active worker to stop."""
    _stop_flag.set()
    return jsonify({"ok": True})


@app.route("/api/stream")
def stream():
    """SSE endpoint – waits for a pending job, runs it, and streams progress."""
    global _pending_job, _active_worker

    TOOLS = {
        "resizer": resizer,
        "watermark": watermark,
        "audio": audio_converter,
        "video": video_compressor,
        "pdf": pdf_compressor,
        "rename": batch_rename,
        "metadata": metadata_stripper,
        "strip_only": strip_only,
    }

    q = queue.Queue()

    def generate():
        global _pending_job, _active_worker
        _stop_flag.clear()

        # Wait for the pending job (the POST comes right after SSE connects)
        job = None
        for _ in range(100):  # up to 5 seconds
            with _pending_lock:
                if _pending_job is not None:
                    job = _pending_job
                    _pending_job = None
                    break
            import time
            time.sleep(0.05)

        if job is None:
            yield f"data: {json.dumps({'type': 'done', 'msg': 'No job received.'})}\n\n"
            return

        tool_mod = TOOLS.get(job["tool"])
        if tool_mod is None:
            yield f"data: {json.dumps({'type': 'done', 'msg': 'Unknown tool.'})}\n\n"
            return

        # Wrap progress_cb to check stop flag
        def progress_cb(event):
            if _stop_flag.is_set() and event.get("type") != "done":
                return  # Suppress events after stop
            _send(q, event)

        def _worker():
            try:
                if job["tool"] == "watermark":
                    watermark.run(INPUT_DIR, OUTPUT_DIR, WATERMARK_DIR, job["options"], progress_cb=progress_cb)
                else:
                    tool_mod.run(INPUT_DIR, OUTPUT_DIR, job["options"], progress_cb=progress_cb)
            except Exception as e:
                _send(q, {"type": "log", "msg": f"FATAL ERROR: {e}"})
                _send(q, {"type": "done", "msg": "Processing aborted due to error."})

        _active_worker = threading.Thread(target=_worker, daemon=True)
        _active_worker.start()

        while True:
            # Check if stop was requested
            if _stop_flag.is_set():
                yield f"data: {json.dumps({'type': 'log', 'msg': '⛔ Processing stopped by user.'})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'msg': 'Stopped. Some files may remain unprocessed in /input.'})}\n\n"
                break

            try:
                event = q.get(timeout=0.5)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "done":
                    break
            except queue.Empty:
                # Check if worker is still alive
                if _active_worker and not _active_worker.is_alive():
                    # Worker finished but no done event — safety net
                    yield f"data: {json.dumps({'type': 'done', 'msg': 'Processing complete.'})}\n\n"
                    break
                # Keep-alive
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _stop_when_browser_closes():
    """Shut down after the browser closes, without breaking a page refresh."""
    global _browser_empty_since
    while True:
        time.sleep(1)
        with _browser_lock:
            now = time.monotonic()
            expired_sessions = [
                session_id
                for session_id, last_seen in _browser_sessions.items()
                if now - last_seen >= HEARTBEAT_TIMEOUT_SECONDS
            ]
            for session_id in expired_sessions:
                del _browser_sessions[session_id]

            if _browser_seen and not _browser_sessions and _browser_empty_since is None:
                _browser_empty_since = now

            close_requested = (
                _browser_empty_since is not None
                and now - _browser_empty_since >= CLOSE_GRACE_PERIOD_SECONDS
            )

        if close_requested:
            if _server is not None:
                _server.shutdown()
            return


if __name__ == "__main__":
    _server = make_server("0.0.0.0", 5000, app, threaded=True)
    threading.Thread(target=_stop_when_browser_closes, daemon=True).start()
    print("\n  OmniTool is running at  http://localhost:5000\n")
    webbrowser.open("http://localhost:5000")
    _server.serve_forever()
