import os
import subprocess
import threading
import select
from gi.repository import GLib
from clipvault.database import add_clip

IMAGE_DIR = os.path.expanduser("~/.local/share/clipvault/images/")
SEP = b"\x00CLIPVAULT_SEP\x00"


class ClipboardMonitor:
    def __init__(self, on_new_clip):
        self.on_new_clip = on_new_clip
        self.last_text = None
        self._running = False
        self._proc = None
        os.makedirs(IMAGE_DIR, exist_ok=True)

    def start(self, display=None):
        wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or \
                  os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"

        if wayland and self._cmd_exists("wl-paste"):
            self._running = True
            print("[ClipVault] Clipboard: wl-paste --watch")
            threading.Thread(target=self._watch_wayland, daemon=True).start()
        elif self._cmd_exists("xclip"):
            self._running = True
            print("[ClipVault] Clipboard: xclip polling")
            threading.Thread(target=self._poll, args=(["xclip", "-selection", "clipboard", "-o"],), daemon=True).start()
        elif self._cmd_exists("xsel"):
            self._running = True
            print("[ClipVault] Clipboard: xsel polling")
            threading.Thread(target=self._poll, args=(["xsel", "--clipboard", "--output"],), daemon=True).start()
        else:
            print("[ClipVault] ERROR: install wl-clipboard or xclip")

    def _watch_wayland(self):
        """
        Single persistent wl-paste --watch process.
        Uses os.read() which returns immediately with available bytes —
        never blocks waiting for a full buffer like read(N) does.
        """
        sep_str = SEP.decode()
        try:
            self._proc = subprocess.Popen(
                ["wl-paste", "--watch", "sh", "-c",
                 f'cat; printf "{sep_str}"'],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            fd = self._proc.stdout.fileno()
            buf = b""

            while self._running:
                # select waits until data is available — no busy loop
                ready, _, _ = select.select([fd], [], [], 1.0)
                if not ready:
                    continue
                # os.read returns whatever bytes are in the pipe RIGHT NOW
                # — never blocks waiting for a full buffer
                chunk = os.read(fd, 65536)
                if not chunk:
                    break  # pipe closed
                buf += chunk
                while SEP in buf:
                    entry, buf = buf.split(SEP, 1)
                    text = entry.decode("utf-8", errors="replace").strip()
                    self._handle(text)

        except Exception as e:
            print(f"[ClipVault] wl-paste --watch error: {e}")
        finally:
            if self._proc:
                try:
                    self._proc.terminate()
                except Exception:
                    pass

    def _poll(self, cmd):
        import time
        while self._running:
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=2)
                if r.returncode == 0:
                    self._handle(r.stdout.decode("utf-8", errors="replace"))
            except Exception:
                pass
            time.sleep(0.5)

    def _handle(self, text):
        if not text or text == self.last_text:
            return
        self.last_text = text
        add_clip('text', content=text, preview=text[:80])
        GLib.idle_add(self._fire, text)

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

    @staticmethod
    def _cmd_exists(name):
        try:
            subprocess.run(["which", name], capture_output=True, check=True, timeout=2)
            return True
        except Exception:
            return False
