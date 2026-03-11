import os
import subprocess
import threading
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")
NULL_SEP = b"\x00"  # null byte separator between clipboard entries


class ClipboardMonitor:
    """
    Architecture:
      wl-paste --watch sh -c 'cat; printf "\\x00"' > FIFO
                                  ^               ^
                              clipboard       null separator
                              on stdin        (signals entry end)

    wl-paste: ONE Wayland connection, persistent, never reconnects.
    sh/cat/printf: NOT Wayland clients — zero new connections = zero blinking.
    FIFO: Python reads from it in background thread, blocks until data arrives.

    Why FIFO and not stdout pipe:
      wl-paste --watch forks COMMAND. Depending on implementation,
      COMMAND may not inherit our stdout pipe cleanly.
      A named FIFO is explicit — both sides open it independently.
    """

    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip
        self.last_text = None
        self._proc = None
        self._running = False
        self._fifo = f"/tmp/.clipvault_{os.getpid()}.fifo"
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display=None):
        # Clean up any stale fifo
        try:
            os.unlink(self._fifo)
        except FileNotFoundError:
            pass
        os.mkfifo(self._fifo, 0o600)

        self._running = True
        # Thread 1: start wl-paste --watch writing to fifo
        threading.Thread(target=self._start_wlpaste, daemon=True).start()
        # Thread 2: read from fifo and process entries
        threading.Thread(target=self._read_fifo, daemon=True).start()
        print("[ClipVault] started (wl-paste --watch → FIFO, no polling, no blinking)")

    def _start_wlpaste(self):
        """ONE persistent wl-paste process. Never restarts unless it dies."""
        try:
            cmd = f"cat; printf '\\x00'"
            self._proc = subprocess.Popen(
                ["wl-paste", "--watch", "sh", "-c", cmd],
                stdout=open(self._fifo, "wb"),
                stderr=subprocess.DEVNULL,
            )
            self._proc.wait()
        except Exception as e:
            print(f"[ClipVault] wl-paste error: {e}")

    def _read_fifo(self):
        """Read from FIFO. Blocks until wl-paste writes. No busy loop."""
        try:
            # Open FIFO for reading — blocks here until wl-paste opens write end
            with open(self._fifo, "rb") as f:
                buf = b""
                while self._running:
                    chunk = f.read(4096)
                    if not chunk:
                        break
                    buf += chunk
                    # Split on null separator
                    while NULL_SEP in buf:
                        entry, buf = buf.split(NULL_SEP, 1)
                        if entry:
                            try:
                                text = entry.decode("utf-8").strip()
                                if text and text != self.last_text:
                                    self.last_text = text
                                    add_clip('text', content=text, preview=text[:80])
                                    GLib.idle_add(self._fire, text)
                            except UnicodeDecodeError:
                                pass  # binary/image — skip
        except Exception as e:
            if self._running:
                print(f"[ClipVault] fifo read error: {e}")

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
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
        try:
            os.unlink(self._fifo)
        except Exception:
            pass
