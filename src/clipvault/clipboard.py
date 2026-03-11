import os
import gi
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


class ClipboardMonitor:
    """
    Uses GTK4 Gdk.Clipboard directly — no subprocess, no Wayland client spawning,
    no blinking, no focus stealing.

    On modern GNOME (41+), Mutter caches clipboard data so read_text_async works
    even when the window is in the background.

    Two triggers:
      1. 'changed' signal  — fires immediately when clipboard changes (event-based)
      2. GLib.timeout_add  — 800ms fallback poll, catches anything signal may miss
    """

    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip  # called with (text,)
        self.last_text = None
        self._reading = False           # guard: no overlapping async reads
        self._clipboard = None
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display):
        self._clipboard = display.get_clipboard()

        # Primary: event-based — fires on every clipboard change
        self._clipboard.connect("changed", self._on_changed)

        # Fallback: slow poll — catches cases where 'changed' fires but
        # read_text_async was busy (guarded by _reading flag)
        GLib.timeout_add(800, self._fallback_poll)

        print("[ClipVault] Clipboard: GTK4 Gdk.Clipboard (no subprocess, no blinking)")

    # ── Triggers ─────────────────────────────────────────────────────────────

    def _on_changed(self, clipboard):
        """Fires when clipboard content changes — triggered by compositor event."""
        self._read()

    def _fallback_poll(self):
        """Slow fallback — only reads if not already reading."""
        self._read()
        return True  # keep repeating

    # ── Read ─────────────────────────────────────────────────────────────────

    def _read(self):
        """Start async clipboard read. Guard prevents overlapping calls."""
        if self._reading or self._clipboard is None:
            return
        self._reading = True
        self._clipboard.read_text_async(None, self._on_text_ready)

    def _on_text_ready(self, clipboard, result):
        """Callback — always in GTK main thread (called by GLib event loop)."""
        self._reading = False
        try:
            text = clipboard.read_text_finish(result)
            if text and text != self.last_text:
                self.last_text = text
                add_clip('text', content=text, preview=text[:80])
                # Already in GTK main thread — call directly
                self.on_new_clip(text)
        except Exception:
            pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    def set_last_text(self, text):
        """Called by SyncServer — prevents phone clips from double-adding."""
        self.last_text = text

    def stop(self):
        pass  # GLib.timeout_add stops when app exits; no threads to kill
