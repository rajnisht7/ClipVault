import os
from gi.repository import GLib, Gdk
from clipvault.database import add_clip

def get_storage_dir():
    return os.path.join(
        os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
        "clipvault"
    )

IMAGE_DIR = os.path.join(get_storage_dir(), "images")


class ClipboardMonitor:


    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip
        self.last_text = None
        self._clipboard = None
        self._reading = False
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display):
        self._clipboard = display.get_clipboard()
        # Poll every 600ms — GTK internal call, no subprocess, no blinking
        GLib.timeout_add(600, self._tick)
        print("[ClipVault] GTK clipboard monitor started (no subprocess)")

    def _tick(self):
        if self._reading:
            return GLib.SOURCE_CONTINUE
        self._reading = True
        # Correct GI signature: read_text_async(cancellable, callback, user_data)
        self._clipboard.read_text_async(None, self._on_text_ready, None)
        return GLib.SOURCE_CONTINUE

    def _on_text_ready(self, clipboard, result, user_data):
        """Callback — always runs in GTK main thread."""
        self._reading = False
        try:
            text = clipboard.read_text_finish(result)
        except Exception as e:
            print(f"[ClipVault] read error: {e}")
            return

        if text and text != self.last_text:
            self.last_text = text
            add_clip('text', content=text, preview=text[:80])
            self.on_new_clip(text)  # already in GTK main thread

    def set_last_text(self, text):
        self.last_text = text

    def stop(self):
        pass  # GLib timer auto-stops when app exits
