import os
import base64
import subprocess
import threading
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip
        self.last_text = None
        self._proc = None
        self._running = False
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display=None):
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            # No --type flag — match any clipboard change
            # base64 -w0 → single line (no internal \n), echo → guaranteed \n
            # readline() always returns immediately
            # sh/base64/echo are NOT Wayland clients → zero blinking
            self._proc = subprocess.Popen(
                ["wl-paste", "--watch", "sh", "-c", "base64 -w0; echo"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            print("[ClipVault] started: wl-paste --watch base64")

            for line in self._proc.stdout:
                if not self._running:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    decoded = base64.b64decode(line)
                    # Try UTF-8 — skip images/binary silently
                    text = decoded.decode("utf-8")
                except Exception:
                    # Not valid base64 or not UTF-8 text (image etc.) — skip
                    continue

                text = text.strip()
                if text and text != self.last_text:
                    self.last_text = text
                    add_clip('text', content=text, preview=text[:80])
                    GLib.idle_add(self._fire, text)

        except FileNotFoundError:
            print("[ClipVault] ERROR: wl-paste not found")
        except Exception as e:
            print(f"[ClipVault] error: {e}")
        finally:
            if self._proc:
                try:
                    self._proc.terminate()
                except Exception:
                    pass

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
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
