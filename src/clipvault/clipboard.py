import os
import base64
import subprocess
import threading
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    """
    wl-paste --type text/plain --watch sh -c 'base64 -w0; echo'

    Why this solves everything:

    BLINKING: Each subprocess.run() = new Wayland connection = compositor
    focus event = blinking. --watch keeps ONE connection open forever.
    base64/sh/echo are NOT Wayland clients. Zero new connections = zero blinking.

    TIMEOUT: wl-paste --no-newline hangs on image/binary clipboard content
    because it waits for the owner app to provide data. --type text/plain
    tells wl-paste "only give me text" — if clipboard has image/file,
    wl-paste skips it instantly instead of hanging.

    READLINE BLOCKING: wl-paste --watch cat outputs "hello" with no \n,
    readline() waits forever. base64 -w0 converts to single-line base64,
    echo adds exactly one \n. readline() always returns immediately.
    Multi-line text also works: "a\nb" → "YQo=" (one line, no internal \n).
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
                ["wl-paste", "--type", "text/plain", "--watch",
                 "sh", "-c", "base64 -w0; echo"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            print("[ClipVault] wl-paste --watch base64 started (1 connection, no blinking)")

            for line in self._proc.stdout:
                if not self._running:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    text = base64.b64decode(line).decode("utf-8", errors="replace")
                except Exception:
                    continue
                if text and text != self.last_text:
                    self.last_text = text
                    add_clip('text', content=text, preview=text[:80])
                    GLib.idle_add(self._fire, text)

        except FileNotFoundError:
            print("[ClipVault] ERROR: wl-paste not found")
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
