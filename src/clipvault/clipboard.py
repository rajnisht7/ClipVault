import os
import subprocess
import threading
import time
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.import os
import subprocess
import threading
import gi
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    """
    Uses Gdk.Clipboard 'changed' signal — fired by the Wayland compositor
    to ALL clients whenever clipboard changes. No polling, no subprocess
    running constantly, zero blinking.

    Content is read via read_text_async (GTK, no subprocess).
    wl-paste is never spawned in a loop — only as fallback if GTK read fails.
    """

    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip  # called with (text,)
        self.last_text = None
        self._clipboard = None
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display):
        self._clipboard = display.get_clipboard()
        # 'changed' fires on every clipboard change — compositor broadcasts it
        # to all Wayland clients including us, regardless of window focus
        self._clipboard.connect("changed", self._on_changed)
        print("[ClipVault] Clipboard: Gdk.Clipboard 'changed' signal (no polling, no blinking)")

    def _on_changed(self, clipboard):
        """Compositor told us clipboard changed — read the content."""
        # Try GTK read first (no subprocess, no Wayland client spawn)
        clipboard.read_text_async(None, self._on_text_ready)

    def _on_text_ready(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                self._handle(text)
                return
        except Exception:
            pass
        # GTK read returned nothing — fall back to wl-paste ONCE (not in a loop)
        self._read_via_wl_paste()

    def _read_via_wl_paste(self):
        """Spawned only when GTK read fails — NOT in a loop."""
        def _run():
            try:
                r = subprocess.run(
                    ["wl-paste", "--no-newline"],
                    capture_output=True, timeout=2
                )
                if r.returncode == 0:
                    text = r.stdout.decode("utf-8", errors="replace")
                    if text:
                        GLib.idle_add(self._handle, text)
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    def _handle(self, text):
        """Must be called in GTK main thread (or via idle_add)."""
        if not text or text == self.last_text:
            return False
        self.last_text = text
        add_clip('text', content=text, preview=text[:80])
        self.on_new_clip(text)
        return False  # for idle_add compatibility

    def set_last_text(self, text):
        """Called by SyncServer — stops phone clips from re-adding."""
        self.last_text = text

    def stop(self):
        pass  # signal-based, nothing to stop
expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    """
    Simple, reliable clipboard polling.

    Wayland: wl-paste --no-newline every 500ms — ONE subprocess, no focus steal.
    X11:     xclip/xsel every 500ms.

    wl-paste --watch was causing blinking because it spawned TWO Wayland
    clients per change (echo + wl-paste --no-newline), stealing focus.
    Simple polling: one process per 500ms, silent, no blinking.
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
            print("[ClipVault] Clipboard: wl-paste polling (Wayland)")
            threading.Thread(target=self._poll, args=(["wl-paste", "--no-newline"],), daemon=True).start()

        elif self._cmd_exists("xclip"):
            self._running = True
            print("[ClipVault] Clipboard: xclip polling (X11)")
            threading.Thread(target=self._poll, args=(["xclip", "-selection", "clipboard", "-o"],), daemon=True).start()

        elif self._cmd_exists("xsel"):
            self._running = True
            print("[ClipVault] Clipboard: xsel polling (X11)")
            threading.Thread(target=self._poll, args=(["xsel", "--clipboard", "--output"],), daemon=True).start()

        else:
            print("[ClipVault] ERROR: No clipboard tool found!")
            print("  Wayland: install wl-clipboard")
            print("  X11:     install xclip")

    def _poll(self, cmd):
        """Poll clipboard every 500ms. One subprocess at a time, no focus steal."""
        while self._running:
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=2)
                if r.returncode == 0:
                    text = r.stdout.decode("utf-8", errors="replace")
                    if text and text != self.last_text:
                        self.last_text = text
                        add_clip('text', content=text, preview=text[:80])
                        GLib.idle_add(self.on_new_clip, text)
            except Exception:
                pass
            time.sleep(0.5)

    def set_last_text(self, text):
        """Called by SyncServer — stops phone clips from re-adding."""
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
