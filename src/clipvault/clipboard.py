import os
import subprocess
import threading
import time
from gi.repository import GLib
from clipvault.database import add_clip


IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    """
    Wayland: event-based via `wl-paste --watch` — readline() blocks until
             clipboard changes, zero CPU, instant response.
    X11:     polling fallback (no native clipboard events on X11).
    """

    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip   # called with (text) — new clip content
        self.last_text = None
        self._running = False
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display=None):
        wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or \
                  os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"

        if wayland and self._cmd_exists("wl-paste"):
            self._running = True
            print("[ClipVault] Clipboard: event-based via wl-paste --watch")
            threading.Thread(target=self._watch_wayland, daemon=True).start()

        elif self._cmd_exists("xclip"):
            self._running = True
            print("[ClipVault] Clipboard: polling via xclip (X11)")
            threading.Thread(target=self._poll_x11, args=("xclip",), daemon=True).start()

        elif self._cmd_exists("xsel"):
            self._running = True
            print("[ClipVault] Clipboard: polling via xsel (X11)")
            threading.Thread(target=self._poll_x11, args=("xsel",), daemon=True).start()

        else:
            print("[ClipVault] WARNING: No clipboard tool found.")
            print("  Wayland: sudo apt install wl-clipboard")
            print("  X11:     sudo apt install xclip")

    # ── Wayland — event-based ─────────────────────────────────────────────────

    def _watch_wayland(self):
        """
        `wl-paste --watch echo` prints a line to stdout on every clipboard change.
        readline() blocks until a change happens — pure event-driven, no CPU waste.
        """
        try:
            proc = subprocess.Popen(
                ["wl-paste", "--watch", "echo", "CLIP_CHANGED"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            while self._running:
                # Blocks here until clipboard changes — no busy loop
                line = proc.stdout.readline()
                if not line:
                    break  # process died
                # Signal received — now read actual clipboard content
                try:
                    result = subprocess.run(
                        ["wl-paste", "--no-newline"],
                        capture_output=True, timeout=2
                    )
                    if result.returncode == 0:
                        text = result.stdout.decode("utf-8", errors="replace")
                        self._handle_new_text(text)
                except Exception:
                    pass
            proc.terminate()
        except Exception as e:
            print(f"[ClipVault] wl-paste --watch failed: {e}, falling back to poll")
            self._poll_wayland_fallback()

    def _poll_wayland_fallback(self):
        """Only used if wl-paste --watch fails for some reason."""
        while self._running:
            try:
                result = subprocess.run(
                    ["wl-paste", "--no-newline"],
                    capture_output=True, timeout=2
                )
                if result.returncode == 0:
                    text = result.stdout.decode("utf-8", errors="replace")
                    self._handle_new_text(text)
            except Exception:
                pass
            time.sleep(0.5)

    # ── X11 — polling (no native events) ─────────────────────────────────────

    def _poll_x11(self, tool):
        while self._running:
            try:
                if tool == "xclip":
                    cmd = ["xclip", "-selection", "clipboard", "-o"]
                else:
                    cmd = ["xsel", "--clipboard", "--output"]
                result = subprocess.run(cmd, capture_output=True, timeout=2)
                if result.returncode == 0:
                    text = result.stdout.decode("utf-8", errors="replace")
                    self._handle_new_text(text)
            except Exception:
                pass
            time.sleep(0.4)

    # ── Shared ────────────────────────────────────────────────────────────────

    def _handle_new_text(self, text):
        if not text or text == self.last_text:
            return
        self.last_text = text
        add_clip('text', content=text, preview=text[:80])
        # Schedule UI update on GTK main thread — pass the text so UI can
        # just append instead of rebuilding everything
        GLib.idle_add(self.on_new_clip, text)

    def set_last_text(self, text):
        """Called by SyncServer so phone clips don't get re-added."""
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
