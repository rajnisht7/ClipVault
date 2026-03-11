import os
import subprocess
import threading
import time
import gi
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")


def _is_flatpak():
    """Flatpak sandbox ke andar /.flatpak-info hamesha exist karta hai."""
    return os.path.exists("/.flatpak-info")


class ClipboardMonitor:
    """
    Flatpak:      GTK4 Gdk.Clipboard 'changed' signal — Wayland pe focus ke
                  bina bhi kaam karta hai, subprocess restriction nahi.
    Non-Flatpak Wayland: wl-paste --watch — event-based, zero CPU.
    Non-Flatpak X11:     xclip/xsel polling — 400ms.
    """

    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip  # called with (text,)
        self.last_text = None
        self._running = False
        self._gdk_clipboard = None
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display):
        if _is_flatpak():
            # ── Flatpak: GTK clipboard directly ──────────────────────────────
            # On Wayland inside Flatpak, Gdk.Clipboard fires 'changed' without
            # needing window focus — Wayland compositor handles it correctly.
            print("[ClipVault] Clipboard: GTK4 Gdk.Clipboard (Flatpak mode)")
            self._gdk_clipboard = display.get_clipboard()
            self._gdk_clipboard.connect("changed", self._on_gtk_changed)

        else:
            # ── Outside Flatpak: system tools ─────────────────────────────────
            wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or \
                      os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"

            if wayland and self._cmd_exists("wl-paste"):
                self._running = True
                print("[ClipVault] Clipboard: wl-paste --watch (Wayland, event-based)")
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
                print("[ClipVault] WARNING: No clipboard tool found.")
                print("  Wayland: sudo apt install wl-clipboard")
                print("  X11:     sudo apt install xclip")

    # ── Flatpak: GTK clipboard ────────────────────────────────────────────────

    def _on_gtk_changed(self, clipboard):
        """Fired by GTK compositor event — no polling, no focus needed on Wayland."""
        clipboard.read_text_async(None, self._on_gtk_text_ready)

    def _on_gtk_text_ready(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            self._handle_new_text(text)
        except Exception:
            pass

    # ── Non-Flatpak Wayland: wl-paste --watch ────────────────────────────────

    def _watch_wayland(self):
        try:
            proc = subprocess.Popen(
                ["wl-paste", "--watch", "echo", "CHANGED"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            while self._running:
                line = proc.stdout.readline()
                if not line:
                    break
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
            print(f"[ClipVault] wl-paste --watch failed ({e}), falling back to poll")
            self._poll_wl_fallback()

    def _poll_wl_fallback(self):
        while self._running:
            try:
                r = subprocess.run(["wl-paste", "--no-newline"],
                                   capture_output=True, timeout=2)
                if r.returncode == 0:
                    self._handle_new_text(r.stdout.decode("utf-8", errors="replace"))
            except Exception:
                pass
            time.sleep(0.5)

    # ── Non-Flatpak X11: xclip/xsel polling ──────────────────────────────────

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
        """Called by SyncServer — prevents phone clips from double-adding."""
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
