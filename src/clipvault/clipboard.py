import os
import subprocess
import threading
import time
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    """
    Simple wl-paste --no-newline polling every 500ms.

    Why not --watch: zwlr_data_control_manager_v1 Wayland protocol is
    restricted inside Flatpak sandbox. --watch never fires.

    Why polling doesn't cause blinking: 500ms interval, one short-lived
    subprocess — not fast enough for compositor to register focus events.
    The blinking seen earlier was from --watch echo + wl-paste running
    two Wayland clients in rapid succession on every clipboard change.

    Binary/image timeout fix: wl-paste hangs on binary content because
    the clipboard owner takes time to encode data. We use a 1s timeout
    and only accept returncode=0. Binary content returns non-zero or
    non-UTF8, both silently skipped.
    """

    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip
        self.last_text = None
        self._running = False
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display=None):
        self._running = True
        threading.Thread(target=self._poll, daemon=True).start()
        print("[ClipVault] Clipboard polling started")

    def _poll(self):
        while self._running:
            try:
                r = subprocess.run(
                    ["wl-paste", "--no-newline"],
                    capture_output=True,
                    timeout=1,          # 1s — binary content gets skipped fast
                )
                if r.returncode == 0 and r.stdout:
                    try:
                        text = r.stdout.decode("utf-8")
                    except UnicodeDecodeError:
                        time.sleep(0.5)
                        continue        # binary/image — skip silently

                    if text and text != self.last_text:
                        self.last_text = text
                        add_clip('text', content=text, preview=text[:80])
                        GLib.idle_add(self._fire, text)

            except subprocess.TimeoutExpired:
                pass                    # binary content — skip silently
            except Exception:
                pass

            time.sleep(0.5)

    def _fire(self, text):
        try:
            self.on_new_clip(text)
        except Exception:
            pass
        return False

    def set_last_text(self, text):
        self.last_text = text

    def stop(self):
        self._running = False
