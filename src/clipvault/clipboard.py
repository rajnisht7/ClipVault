import os
import subprocess
import threading
import time
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    """
    wl-paste --no-newline polling with os.setsid() isolation.

    Blinking cause: wl-paste inherits ClipVault's Wayland session/process group.
    Compositor sees a child of a GUI app connecting → sends focus events to parent
    → ClipVault window briefly gets focus signal → screen blinks.

    Fix: os.setsid() creates a new process session for wl-paste, completely
    detached from ClipVault. Compositor treats it as an independent process,
    sends zero focus events to ClipVault → zero blinking.
    """

    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip
        self.last_text = None
        self._running = False
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display=None):
        self._running = True
        threading.Thread(target=self._poll, daemon=True).start()
        print("[ClipVault] Clipboard polling started (setsid isolated)")

    def _poll(self):
        while self._running:
            try:
                r = subprocess.run(
                    ["wl-paste", "--no-newline"],
                    capture_output=True,
                    timeout=1,
                    # Key fix: new session = fully detached from ClipVault
                    # Compositor won't send focus events to ClipVault
                    preexec_fn=os.setsid,
                )
                if r.returncode == 0 and r.stdout:
                    try:
                        text = r.stdout.decode("utf-8")
                    except UnicodeDecodeError:
                        time.sleep(0.5)
                        continue
                    if text and text != self.last_text:
                        self.last_text = text
                        add_clip('text', content=text, preview=text[:80])
                        GLib.idle_add(self._fire, text)
            except subprocess.TimeoutExpired:
                pass
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
