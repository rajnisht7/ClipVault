import os
import subprocess
import threading
import time
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    """
    Uses xclip over X11/XWayland to monitor clipboard.

    Why this works in Flatpak:
    - Manifest has --socket=x11 (not fallback-x11) → DISPLAY=:0 always set
    - --share=ipc → XWayland shared memory works
    - GNOME shell syncs Wayland clipboard ↔ X11 clipboard automatically
    - xclip reads X11 clipboard → gets everything copied anywhere
    - Background thread → no focus needed, no blinking
    """

    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip
        self.last_text = None
        self._running = False
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display=None):
        # Force DISPLAY if not set (safety net)
        if not os.environ.get("DISPLAY"):
            os.environ["DISPLAY"] = ":0"

        print(f"[ClipVault] DISPLAY={os.environ.get('DISPLAY')}")
        print(f"[ClipVault] WAYLAND_DISPLAY={os.environ.get('WAYLAND_DISPLAY', 'not set')}")

        self._running = True
        threading.Thread(target=self._poll, daemon=True).start()
        print("[ClipVault] Clipboard monitor started (xclip, background thread)")

    def _poll(self):
        env = dict(os.environ)
        # Ensure DISPLAY is in subprocess env
        env.setdefault("DISPLAY", ":0")

        while self._running:
            try:
                r = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    capture_output=True,
                    timeout=2,
                    env=env
                )
                if r.returncode == 0:
                    text = r.stdout.decode("utf-8", errors="replace")
                    if text and text != self.last_text:
                        self.last_text = text
                        add_clip('text', content=text, preview=text[:80])
                        GLib.idle_add(self._fire, text)
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
