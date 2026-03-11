import os
import base64
import subprocess
import threading
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    """
    wl-paste --watch sh -c 'base64 -w0; echo'

    The readline() bug:
      wl-paste --watch cat → cat writes "hello" with NO newline
      readline() waits forever for \n → nothing ever shows up

    The fix — base64:
      base64 -w0  → encodes clipboard content, output has NO internal newlines
      echo        → adds exactly ONE \n at the end
      readline()  → returns immediately, always

    Multi-line clipboard content also works because base64 encoding
    removes all newlines from the content itself.

    ONE persistent wl-paste Wayland connection. base64/sh/echo are NOT
    Wayland clients. Zero new connections per clipboard change = zero blinking.
    """

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
            self._proc = subprocess.Popen(
                ["wl-paste", "--watch", "sh", "-c", "base64 -w0; echo"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            print("[ClipVault] Clipboard monitor started (wl-paste --watch base64)")

            for raw_line in self._proc.stdout:
                if not self._running:
                    break
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    text = base64.b64decode(raw_line).decode("utf-8", errors="replace")
                except Exception:
                    continue
                if text and text != self.last_text:
                    self.last_text = text
                    add_clip('text', content=text, preview=text[:80])
                    GLib.idle_add(self._fire, text)

        except FileNotFoundError:
            print("[ClipVault] ERROR: wl-paste not found.")
        except Exception as e:
            print(f"[ClipVault] Error: {e}")
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
