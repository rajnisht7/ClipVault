import os
import subprocess
import threading
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")
SEP = b"CLIPVAULT_SEP"


class ClipboardMonitor:
    """
    Wayland: ONE persistent wl-paste --watch process.
      - wl-paste holds a single Wayland connection permanently
      - On each clipboard change, it pipes content to: sh -c 'cat; printf CLIPVAULT_SEP'
      - 'sh' and 'cat' are NOT Wayland clients — zero new connections = zero blinking
      - We read stdout, split on CLIPVAULT_SEP to get each clipboard entry

    X11: xclip/xsel polling (no native events on X11).
    """

    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip  # called with (text,)
        self.last_text = None
        self._running = False
        self._proc = None
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display=None):
        wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or \
                  os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"

        if wayland and self._cmd_exists("wl-paste"):
            self._running = True
            print("[ClipVault] Clipboard: wl-paste --watch (one persistent connection, no blinking)")
            threading.Thread(target=self._watch, daemon=True).start()

        elif self._cmd_exists("xclip"):
            self._running = True
            print("[ClipVault] Clipboard: xclip polling (X11)")
            threading.Thread(target=self._poll_x11, args=(
                ["xclip", "-selection", "clipboard", "-o"],), daemon=True).start()

        elif self._cmd_exists("xsel"):
            self._running = True
            print("[ClipVault] Clipboard: xsel polling (X11)")
            threading.Thread(target=self._poll_x11, args=(
                ["xsel", "--clipboard", "--output"],), daemon=True).start()

        else:
            print("[ClipVault] ERROR: No clipboard tool. Install wl-clipboard or xclip.")

    # ── Wayland ───────────────────────────────────────────────────────────────

    def _watch(self):
        """
        Start ONE wl-paste --watch process. It stays alive forever.
        On each clipboard change wl-paste pipes content to sh+cat, then prints SEP.
        We accumulate stdout bytes and split on SEP to get each entry.

        wl-paste = 1 Wayland connection, always open, never spawns more.
        sh/cat   = NOT Wayland clients. No new connections. No blinking.
        """
        try:
            self._proc = subprocess.Popen(
                ["wl-paste", "--watch", "sh", "-c",
                 f"cat; printf '{SEP.decode()}'"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            buf = b""
            while self._running:
                chunk = self._proc.stdout.read(256)
                if not chunk:
                    break  # process died
                buf += chunk
                # Split on sentinel — each clipboard entry ends with SEP
                while SEP in buf:
                    entry, buf = buf.split(SEP, 1)
                    text = entry.decode("utf-8", errors="replace")
                    self._handle(text)
        except Exception as e:
            print(f"[ClipVault] wl-paste --watch failed: {e}")

    def _poll_x11(self, cmd):
        import time
        while self._running:
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=2)
                if r.returncode == 0:
                    self._handle(r.stdout.decode("utf-8", errors="replace"))
            except Exception:
                pass
            time.sleep(0.5)

    # ── Shared ────────────────────────────────────────────────────────────────

    def _handle(self, text):
        text = text.strip()
        if not text or text == self.last_text:
            return
        self.last_text = text
        add_clip('text', content=text, preview=text[:80])
        GLib.idle_add(self.on_new_clip, text)

    def set_last_text(self, text):
        """Called by SyncServer — prevents phone clips from double-adding."""
        self.last_text = text

    def stop(self):
        self._running = False
        if self._proc:
            self._proc.terminate()

    @staticmethod
    def _cmd_exists(name):
        try:
            subprocess.run(["which", name], capture_output=True,
                           check=True, timeout=2)
            return True
        except Exception:
            return False
