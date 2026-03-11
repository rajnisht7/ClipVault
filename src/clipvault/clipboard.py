import os
import subprocess
import threading
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    """
    How wl-paste --watch works:
      1. wl-paste connects to Wayland compositor ONCE and stays connected
      2. Compositor notifies wl-paste when clipboard changes (wl_data_device protocol)
      3. wl-paste runs our command (cat) with new clipboard content on stdin
      4. 'cat' is NOT a Wayland client — it just reads stdin and writes stdout
      5. We read wl-paste's stdout line by line

    Result: ONE persistent Wayland connection, zero new connections per change,
    zero focus requirement, zero blinking.

    Why not xclip: Flatpak with --socket=wayland does NOT set DISPLAY, so xclip
    fails with "Can't open display".

    Why not GTK read_text_async: Wayland security model requires window focus for
    clipboard reads — by protocol design, not a GTK bug.
    """

    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip
        self.last_text = None
        self._proc = None
        self._running = False
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display=None):
        self._running = True
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        """
        wl-paste --watch cat:
          - wl-paste keeps ONE Wayland connection open forever
          - On each clipboard change, it pipes the content to 'cat' on stdin
          - cat writes it to stdout, then wl-paste adds a newline
          - We readline() — blocks until next change (zero CPU, truly event-based)
        """
        try:
            self._proc = subprocess.Popen(
                ["wl-paste", "--watch", "cat"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            print("[ClipVault] Clipboard: wl-paste --watch cat (1 connection, event-based)")

            buf = b""
            while self._running:
                # readline() blocks until wl-paste signals a clipboard change
                # This is the key — zero CPU usage while waiting
                chunk = self._proc.stdout.readline()
                if not chunk:
                    break  # wl-paste died

                buf += chunk

                # wl-paste adds a newline after each clipboard entry
                # For multi-line text, we accumulate until we get a blank line
                # or until readline returns with content
                text = buf.decode("utf-8", errors="replace").rstrip("\n")
                buf = b""

                if text and text != self.last_text:
                    self.last_text = text
                    add_clip('text', content=text, preview=text[:80])
                    GLib.idle_add(self._fire, text)

        except FileNotFoundError:
            print("[ClipVault] ERROR: wl-paste not found. Install wl-clipboard.")
        except Exception as e:
            print(f"[ClipVault] wl-paste error: {e}")
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
        """Called by SyncServer to prevent phone clips from double-adding."""
        self.last_text = text

    def stop(self):
        self._running = False
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
