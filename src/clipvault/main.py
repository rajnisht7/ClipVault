import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio
import sys
from clipvault.database import init_db
from clipvault.window import ClipVaultWindow


class ClipVaultApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.rajnisht7.ClipVault",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        init_db()
        self.win = ClipVaultWindow(application=app)
        self.win.start_monitor(self.win.get_display())
        self.win.present()


def main():
    app = ClipVaultApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    main()
