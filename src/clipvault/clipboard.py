import os
import subprocess
import threading
import time
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    """
    Uses xclip to poll X11 clipboard in a background thread.

    Why xclip and not wl-paste or GTK clipboard:
    - wl-paste inside Flatpak: Wayland socket restricted → returns empty
    - GTK read_text_async on Wayland: requires window focus
    - xclip uses X11 (available via --socket=fallback-x11 in Flatpak manifest)
    - GNOME shell automatically syncs Wayland clipboard → X11 clipboard
    - So xclip sees everything copied anywhere, with no focus requirement
    - Background thread = no GLib/GTK calls = no blinking
    """

    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip
        self.last_text = None
        self._running = False
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display=None):
        if self._cmd_exists("xclip"):
            self._running = True
            print("[ClipVault] Clipboard: xclip polling via X11 (background, no focus needed)")
            threading.Thread(target=self._poll, daemon=True).start()
        else:
            # xclip not found — fall back to GTK timer (focus-dependent but better than nothing)
            print("[ClipVault] WARNING: xclip not found, falling back to GTK clipboard")
            print("[ClipVault] Install xclip for background clipboard monitoring")
            self._clipboard = display.get_clipboard() if display else None
            if self._clipboard:
                GLib.timeout_add(500, self._gtk_tick)

    def _poll(self):
        """Background thread — polls xclip every 500ms. No Wayland clients = no blinking."""
        while self._running:
            try:
                r = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    capture_output=True, timeout=2
                )
                if r.returncode == 0:
                    text = r.stdout.decode("utf-8", errors="replace")
                    if text and text != self.last_text:
                        self.last_text = text
                        add_clip('text', content=text, preview=text[:80])
                        GLib.idle_add(self._fire, text)
            except Exception:
                pass
            time.sleep(0.5)

    # GTK fallback (only if xclip missing)
    def _gtk_tick(self):
        if not getattr(self, '_reading', False):
            self._reading = True
            self._clipboard.read_text_async(None, self._gtk_done)
        return True

    def _gtk_done(self, clipboard, result):
        self._reading = False
        try:
            text = clipboard.read_text_finish(result)
            if text and text != self.last_text:
                self.last_text = text
                add_clip('text', content=text, preview=text[:80])
                self._fire(text)
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

    @staticmethod
    def _cmd_exists(name):
        try:
            subprocess.run(["which", name], capture_output=True, check=True, timeout=2)
            return True
        except Exception:
            return False
