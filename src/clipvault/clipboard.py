import os
import subprocess
import threading
import time
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    """
    Wayland (Flatpak + non-Flatpak): wl-paste --watch
      - wl-clipboard is bundled in Flatpak manifest
      - --socket=wayland gives it full compositor access
      - event-based, zero CPU, no focus needed

    X11 fallback: xclip/xsel polling every 400ms
    """

    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip  # called with (text,)
        self.last_text = None
        self._running = False
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display=None):
        wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or \
                  os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"

        if wayland and self._cmd_exists("wl-paste"):
            self._running = True
            print("[ClipVault] Clipboard: wl-paste --watch (event-based, focus-independent)")
            threading.Thread(target=self._watch_wayland, daemon=True).start()

        elif self._cmd_exists("xclip"):
            self._running = True
            print("[ClipVault] Clipboard: xclip polling (X11)")
            threading.Thread(target=self._poll_x11, args=("xclip",), daemon=True).start()

        elif self._cmd_exists("xsel"):
            self._running = True
            print("[ClipVault] Clipboard: xsel polling (X11)")
            threading.Thread(target=self._poll_x11, args=("xsel",), daemon=True).start()

        else:
            print("[ClipVault] ERROR: No clipboard tool found!")
            print("  Wayland: install wl-clipboard")
            print("  X11:     install xclip")

    # ── Wayland ───────────────────────────────────────────────────────────────

    def _watch_wayland(self):
        """
        wl-paste --watch echo CHANGED fires on every clipboard change.
        readline() blocks — zero CPU, instant, no window focus needed.
        Works inside Flatpak because --socket=wayland is in finish-args.
        """
        try:
            proc = subprocess.Popen(
                ["wl-paste", "--watch", "echo", "CHANGED"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            while self._running:
                line = proc.stdout.readline()
                if not line:
                    break  # process died — fall to poll
                # Clipboard changed — read the actual content
                try:
                    r = subprocess.run(
                        ["wl-paste", "--no-newline"],
                        capture_output=True, timeout=2
                    )
                    if r.returncode == 0:
                        text = r.stdout.decode("utf-8", errors="replace")
                        self._handle_new_text(text)
                except Exception:
                    pass
            proc.terminate()
        except Exception as e:
            print(f"[ClipVault] wl-paste --watch failed ({e}), falling back to poll")

        # Fallback: poll if --watch failed
        self._poll_wl()

    def _poll_wl(self):
        """Polling fallback — only if wl-paste --watch dies unexpectedly."""
        print("[ClipVault] Clipboard: wl-paste polling fallback")
        while self._running:
            try:
                r = subprocess.run(
                    ["wl-paste", "--no-newline"],
                    capture_output=True, timeout=2
                )
                if r.returncode == 0:
                    self._handle_new_text(r.stdout.decode("utf-8", errors="replace"))
            except Exception:
                pass
            time.sleep(0.5)

    # ── X11 ───────────────────────────────────────────────────────────────────

    def _poll_x11(self, tool):
        while self._running:
            try:
                cmd = (["xclip", "-selection", "clipboard", "-o"]
                       if tool == "xclip" else ["xsel", "--clipboard", "--output"])
                r = subprocess.run(cmd, capture_output=True, timeout=2)
                if r.returncode == 0:
                    self._handle_new_text(r.stdout.decode("utf-8", errors="replace"))
            except Exception:
                pass
            time.sleep(0.4)

    # ── Shared ────────────────────────────────────────────────────────────────

    def _handle_new_text(self, text):
        if not text or text == self.last_text:
            return
        self.last_text = text
        add_clip('text', content=text, preview=text[:80])
        GLib.idle_add(self.on_new_clip, text)

    def set_last_text(self, text):
        """Called by SyncServer — stops phone clips from re-adding."""
        self.last_text = text

    def stop(self):
        self._running = False

    @staticmethod
    def _cmd_exists(name):
        try:
            subprocess.run(["which", name], capture_output=True,
                           check=True, timeout=2)
            return True
        except Exception:
            return False
