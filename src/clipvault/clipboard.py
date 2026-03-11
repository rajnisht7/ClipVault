import os
import gi
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    """
    Pure GTK4 approach — no subprocess, no blinking.

    Uses GLib.timeout_add(500ms) to call read_text_async.
    On GNOME, gnome-shell caches clipboard data so read_text_async
    works even when window is not focused.

    No 'changed' signal dependency — timer catches everything.
    """

    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip
        self.last_text = None
        self._clipboard = None
        self._reading = False
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display):
        self._clipboard = display.get_clipboard()
        # 500ms timer — pure GTK, no subprocess, no blinking
        GLib.timeout_add(500, self._tick)
        print("[ClipVault] Clipboard monitor started (GTK timer, 500ms)")

    def _tick(self):
        """Called every 500ms by GLib main loop — always in GTK main thread."""
        if not self._reading:
            self._reading = True
            self._clipboard.read_text_async(None, self._on_done)
        return True  # keep repeating

    def _on_done(self, clipboard, result):
        """Callback from read_text_async — always in GTK main thread."""
        self._reading = False
        try:
            text = clipboard.read_text_finish(result)
            if text and text != self.last_text:
                self.last_text = text
                add_clip('text', content=text, preview=text[:80])
                self.on_new_clip(text)
        except Exception:
            pass

    def set_last_text(self, text):
        """Called by SyncServer — prevents phone clips from double-adding."""
        self.last_text = text

    def stop(self):
        pass
