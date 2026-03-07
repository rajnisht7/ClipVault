import os
import subprocess
import threading
import time
import hashlib
from datetime import datetime
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    """
    Polls system clipboard tools in a background thread.
    Completely independent of window focus — works even when minimized.

    Wayland: polls `wl-paste --no-newline` every 400ms
    X11:     polls `xclip -o` or `xsel -o` every 400ms
    """

    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip
        self.last_text = None
        self._running = False
        self._thread = None
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display=None):
        # Detect which tool to use
        wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or \
                  os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"

        if wayland and self._cmd_exists("wl-paste"):
            self._tool = "wl-paste"
        elif self._cmd_exists("xclip"):
            self._tool = "xclip"
        elif self._cmd_exists("xsel"):
            self._tool = "xsel"
        else:
            self._tool = None

        if self._tool is None:
            # Nothing available — log and give up
            print("[ClipVault] WARNING: No clipboard tool found.")
            print("  Wayland: install wl-clipboard  (sudo apt install wl-clipboard)")
            print("  X11:     install xclip          (sudo apt install xclip)")
            return

        print(f"[ClipVault] Clipboard monitor using: {self._tool}")
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        """Background thread — polls clipboard every 400ms, no focus needed."""
        while self._running:
            try:
                text = self._read_clipboard()
                if text is not None and text != self.last_text:
                    self.last_text = text
                    add_clip('text', content=text, preview=text[:80])
                    # Must use idle_add — we're in a background thread
                    GLib.idle_add(self._fire)
            except Exception:
                pass
            time.sleep(0.4)

    def _read_clipboard(self):
        """Read current clipboard text using the available system tool."""
        if self._tool == "wl-paste":
            cmd = ["wl-paste", "--no-newline"]
        elif self._tool == "xclip":
            cmd = ["xclip", "-selection", "clipboard", "-o"]
        elif self._tool == "xsel":
            cmd = ["xsel", "--clipboard", "--output"]
        else:
            return None

        result = subprocess.run(cmd, capture_output=True, timeout=2)
        if result.returncode != 0:
            return None
        return result.stdout.decode("utf-8", errors="replace")

    def _fire(self):
        """Called via GLib.idle_add — always runs in GTK main thread."""
        try:
            self.on_new_clip()
        except Exception:
            pass
        return False  # do not repeat

    def set_last_text(self, text):
        """Called by SyncServer when phone sends a clip — prevents double-add."""
        self.last_text = text

    def stop(self):
        self._running = False

    @staticmethod
    def _cmd_exists(name):
        try:
            subprocess.run(["which", name], capture_output=True, check=True, timeout=2)
            return True
        except Exception:
            return False
