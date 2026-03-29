import asyncio
import json
import socket
import threading
import websockets
from clipvault.database import add_clip, get_clips


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 8))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def find_free_port(start=8765, end=8780):
    """Find first free port in range."""
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    return start  # fallback


class SyncServer:
    def __init__(self, on_new_clip, on_connection_change=None, port=8765):
        self.on_new_clip = on_new_clip
        self.on_connection_change = on_connection_change
        self.port = find_free_port(port)  # auto-pick free port
        self.clients = set()
        self.loop = None
        self.thread = None
        self._gtk_display = None
        self._clipboard_monitor = None

    def set_display(self, display):
        self._gtk_display = display

    def set_clipboard_monitor(self, monitor):
        self._clipboard_monitor = monitor

    def get_url(self):
        return f"ws://{get_local_ip()}:{self.port}"

    def get_phone_url(self):
        return f"http://{get_local_ip()}:{self.port + 1}"

    def get_connected_count(self):
        return len(self.clients)

    def start(self):
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def _run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._serve())

    async def _serve(self):
        ws_server = websockets.serve(self._handler, "0.0.0.0", self.port)
        http_task = self._serve_http()
        await asyncio.gather(ws_server, http_task)
        await asyncio.Future()

    async def _handler(self, websocket):
        self.clients.add(websocket)
        self._notify_connection_change()
        try:
            clips = get_clips(limit=30)
            recent = [
                {"type": "text", "content": c[2], "preview": c[4], "timestamp": c[5]}
                for c in clips if c[1] == 'text' and c[2]
            ]
            await websocket.send(json.dumps({"action": "history", "clips": recent}))

            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get("action") == "clip" and data.get("content"):
                        content = data["content"]
                        add_clip('text', content=content, preview=content[:80])
                        self._update_monitor_last_text(content)
                        self._set_gtk_clipboard(content)
                        from gi.repository import GLib
                        GLib.idle_add(self._safe_refresh)
                        await self._broadcast(
                            json.dumps({"action": "clip", "content": content, "preview": content[:80]}),
                            exclude=websocket
                        )
                except Exception:
                    pass
        finally:
            self.clients.discard(websocket)
            self._notify_connection_change()

    def _update_monitor_last_text(self, text):
        from gi.repository import GLib
        def _do():
            if self._clipboard_monitor:
                self._clipboard_monitor.set_last_text(text)
            return False
        GLib.idle_add(_do)

    def _set_gtk_clipboard(self, content):
        from gi.repository import GLib
        def _do():
            try:
                if self._gtk_display:
                    self._gtk_display.get_clipboard().set(content)
            except Exception:
                pass
            return False
        GLib.idle_add(_do)

    def _safe_refresh(self):
        try:
            self.on_new_clip()
        except Exception:
            pass
        return False

    def _notify_connection_change(self):
        if self.on_connection_change:
            from gi.repository import GLib
            count = len(self.clients)
            GLib.idle_add(self.on_connection_change, count)

    async def _broadcast(self, message, exclude=None):
        for client in list(self.clients):
            if client != exclude:
                try:
                    await client.send(message)
                except Exception:
                    self.clients.discard(client)

    def broadcast_from_pc(self, content):
        if self.loop and self.clients:
            msg = json.dumps({"action": "clip", "content": content, "preview": content[:80]})
            asyncio.run_coroutine_threadsafe(self._broadcast(msg), self.loop)

    async def _serve_http(self):
        import http.server
        import socketserver
        from clipvault.phone_ui import PHONE_HTML

        port = self.port + 1
        html = PHONE_HTML.replace("{{WS_PORT}}", str(self.port))

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode())
            def log_message(self, *a):
                pass

        def run():
            with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd:
                httpd.serve_forever()

        await asyncio.to_thread(run)
