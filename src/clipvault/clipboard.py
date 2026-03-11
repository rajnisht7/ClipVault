import os
import base64
import subprocess
import threading
import tempfile
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    """
    wl-paste --watch does NOT pipe command stdout to wl-paste's stdout.
    The command's output goes to the inherited terminal, not our pipe.
    That's why all previous base64/cat approaches read nothing from stdout.

    Fix: write clipboard content to a temp file, signal via stdout echo.
      wl-paste --watch sh -c 'base64 -w0 > TMPFILE; echo READY'
        - wl-paste: ONE Wayland connection
        - sh/base64/echo: NOT Wayland clients → zero blinking
        - base64 output → temp file (avoids stdout pipe issue)
        - echo READY → goes to wl-paste's stdout → our readline()
        - Python: reads READY signal → opens temp file → decodes base64
    """

    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip
        self.last_text = None
        self._proc = None
        self._running = False
        self._tmp = os.path.join(tempfile.gettempdir(),
                                 f".clipvault_{os.getpid()}")
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display=None):
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            cmd = f"base64 -w0 > {self._tmp}; echo READY"
            self._proc = subprocess.Popen(
                ["wl-paste", "--watch", "sh", "-c", cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            print("[ClipVault] started: wl-paste --watch (temp file method)")

            for line in self._proc.stdout:
                if not self._running:
                    break
                if b"READY" not in line:
                    continue
                # Signal received — read temp file
                try:
                    with open(self._tmp, "rb") as f:
                        raw = f.read().strip()
                    if not raw:
                        continue
                    text = base64.b64decode(raw).decode("utf-8")
                    text = text.strip()
                    if text and text != self.last_text:
                        self.last_text = text
                        add_clip('text', content=text, preview=text[:80])
                        GLib.idle_add(self._fire, text)
                except Exception:
                    # Binary/image clipboard — skip silently
                    pass

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
            try:
                os.unlink(self._tmp)
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
