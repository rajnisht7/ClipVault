import os
import subprocess
import threading
import time
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip
        self.last_text = None
        self._running = False
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display=None):
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        """
        Simple approach: poll wl-paste --no-newline every 500ms.
        Most reliable method inside Flatpak with --socket=wayland.
        """
        print(f"[CV] start. WAYLAND={os.environ.get('WAYLAND_DISPLAY')} DISPLAY={os.environ.get('DISPLAY')}")

        # First verify wl-paste works at all
        test = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, timeout=3)
        print(f"[CV] wl-paste test: returncode={test.returncode} stderr={test.stderr[:100]}")

        while self._running:
            try:
                r = subprocess.run(
                    ["wl-paste", "--no-newline"],
                    capture_output=True,
                    timeout=3
                )
                if r.returncode == 0:
                    text = r.stdout.decode("utf-8", errors="replace")
                    if text and text != self.last_text:
                        print(f"[CV] new clip: {text[:40]!r}")
                        self.last_text = text
                        add_clip('text', content=text, preview=text[:80])
                        GLib.idle_add(self._fire, text)
                else:
                    # returncode 1 = empty clipboard (normal), anything else = error
                    if r.returncode != 1:
                        print(f"[CV] wl-paste error rc={r.returncode}: {r.stderr[:80]}")
            except Exception as e:
                print(f"[CV] exception: {e}")
            time.sleep(0.5)

    def _fire(self, text):
        try:
            self.on_new_clip(text)
        except Exception as e:
            print(f"[CV] fire error: {e}")
        return False

    def set_last_text(self, text):
        self.last_text = text

    def stop(self):
        self._running = False
