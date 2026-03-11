import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GdkPixbuf, GLib
import tempfile
import os


class QRDialog(Adw.Dialog):
    def __init__(self, phone_url, ws_url, sync_server):
        super().__init__()
        self.set_title("Connect Phone")
        self.set_content_width(320)
        self.sync_server = sync_server

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        title = Gtk.Label(label="📱 Scan to Connect")
        title.add_css_class("title-2")
        box.append(title)

        sub = Gtk.Label(label="Open your phone camera and\nscan the QR code")
        sub.set_justify(Gtk.Justification.CENTER)
        sub.add_css_class("dim-label")
        box.append(sub)

        qr_image = self._generate_qr_widget(phone_url)
        box.append(qr_image)

        url_row = Adw.ActionRow()
        url_row.set_title(phone_url)
        url_row.set_subtitle("Or open this URL manually")
        copy_btn = Gtk.Button(label="Copy")
        copy_btn.set_valign(Gtk.Align.CENTER)
        copy_btn.add_css_class("pill")
        copy_btn.connect("clicked", self._on_copy_url, phone_url)
        url_row.add_suffix(copy_btn)
        box.append(url_row)

        # ✅ Live status label — updated by SyncServer callback
        self.status_label = Gtk.Label()
        self.status_label.add_css_class("dim-label")
        box.append(self.status_label)
        self._update_status(sync_server.get_connected_count())

        # Register callback so status auto-updates when phone connects/disconnects
        self.sync_server.on_connection_change = self._update_status

        close_btn = Gtk.Button(label="Done")
        close_btn.add_css_class("pill")
        close_btn.add_css_class("suggested-action")
        close_btn.connect("clicked", self._on_close)
        box.append(close_btn)

        self.set_child(box)

    def _update_status(self, count):
        if count > 0:
            self.status_label.set_label(f"🟢 {count} phone(s) connected")
        else:
            self.status_label.set_label("🔴 No phone connected")
        return False  # for GLib.idle_add compatibility

    def _generate_qr_widget(self, url):
        try:
            import qrcode
            qr = qrcode.QRCode(box_size=6, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            img.save(tmp.name)
            tmp.close()

            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(tmp.name, 240, 240, True)
            os.unlink(tmp.name)

            picture = Gtk.Picture.new_for_pixbuf(pixbuf)
            picture.set_size_request(240, 240)
            picture.set_halign(Gtk.Align.CENTER)
            return picture
        except Exception as e:
            label = Gtk.Label(label=f"QR unavailable\nInstall: pip install qrcode[pil]\n\n{e}")
            label.add_css_class("dim-label")
            label.set_justify(Gtk.Justification.CENTER)
            return label

    def _on_copy_url(self, btn, url):
        display = self.get_display()
        if display:
            display.get_clipboard().set(url)

    def _on_close(self, btn):
        # Restore the original on_connection_change when dialog closes
        self.sync_server.on_connection_change = None
        self.close()
