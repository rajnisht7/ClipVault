import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, GLib, GdkPixbuf
from clipvault.database import get_clips, toggle_pin, delete_clip, clear_all
from clipvault.clipboard import ClipboardMonitor
from clipvault.sync_server import SyncServer


class ClipVaultWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("ClipVault")
        self.set_default_size(420, 600)

        self.monitor = ClipboardMonitor(on_new_clip=self._on_pc_clip)

        self.sync_server = SyncServer(
            on_new_clip=self._refresh,
            on_connection_change=self._on_connection_change
        )
        # Give sync_server a reference to monitor so phone clips don't double-fire
        self.sync_server.set_clipboard_monitor(self.monitor)
        self.sync_server.start()

        # ── Layout ──────────────────────────────────────────────
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        header = Adw.HeaderBar()
        header.set_centering_policy(Adw.CenteringPolicy.STRICT)

        self.window_title = Adw.WindowTitle()
        self.window_title.set_title("ClipVault")
        self.window_title.set_subtitle("Clipboard History")
        header.set_title_widget(self.window_title)

        phone_btn = Gtk.Button()
        phone_btn.set_icon_name("phone-symbolic")
        phone_btn.set_tooltip_text("Connect Phone")
        phone_btn.add_css_class("flat")
        phone_btn.connect("clicked", self._on_phone_connect)
        header.pack_start(phone_btn)

        clear_btn = Gtk.Button(label="Clear")
        clear_btn.add_css_class("destructive-action")
        clear_btn.connect("clicked", self._on_clear)
        header.pack_end(clear_btn)

        toolbar_view.add_top_bar(header)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        toolbar_view.set_content(content_box)

        search_bar = Gtk.SearchBar()
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search clipboard history...")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self._on_search)
        search_bar.set_child(self.search_entry)
        search_bar.set_search_mode(True)
        content_box.append(search_bar)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content_box.append(scrolled)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("boxed-list")
        self.list_box.set_margin_top(8)
        self.list_box.set_margin_bottom(8)
        self.list_box.set_margin_start(12)
        self.list_box.set_margin_end(12)
        scrolled.set_child(self.list_box)

        self._refresh()

    def start_monitor(self, display):
        self.sync_server.set_display(display)
        self.monitor.start(display)
        # Clean up monitor thread when window is destroyed
        self.connect("destroy", lambda _: self.monitor.stop())

    # ── Callbacks ────────────────────────────────────────────────

    def _on_pc_clip(self):
        """Called from ClipboardMonitor — already in GTK main thread."""
        self._refresh()
        clips = get_clips(limit=1)
        if clips:
            _, clip_type, content, _, _, _, _ = clips[0]
            if clip_type == 'text' and content:
                self.sync_server.broadcast_from_pc(content)

    def _refresh(self):
        """Rebuild clip list. Must always be in GTK main thread."""
        search = self.search_entry.get_text() if hasattr(self, 'search_entry') else ""
        clips = get_clips(search=search)
        self._populate(clips)

    def _on_search(self, entry):
        self._refresh()

    def _on_connection_change(self, count):
        """Called via GLib.idle_add — GTK-safe."""
        if count > 0:
            self.window_title.set_subtitle(f"📱 {count} phone connected")
        else:
            self.window_title.set_subtitle("Clipboard History")
        return False

    def _on_phone_connect(self, btn):
        try:
            from clipvault.qr_dialog import QRDialog
            dialog = QRDialog(
                self.sync_server.get_phone_url(),
                self.sync_server.get_url(),
                self.sync_server
            )
            dialog.present(self)
        except ImportError:
            dialog = Adw.AlertDialog()
            dialog.set_heading("Connect Your Phone")
            dialog.set_body(
                f"Open this URL on your phone:\n\n{self.sync_server.get_phone_url()}"
                "\n\n(Install 'qrcode[pil]' for QR code)"
            )
            dialog.add_response("ok", "OK")
            dialog.present(self)

    # ── List population ──────────────────────────────────────────

    def _populate(self, clips):
        # Walk sibling chain — correct way to remove all GTK4 ListBox children
        child = self.list_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.list_box.remove(child)
            child = nxt

        if not clips:
            row = Adw.ActionRow()
            row.set_title("No clips found")
            row.set_subtitle("Copy something to get started!")
            self.list_box.append(row)
            return

        for clip in clips:
            clip_id, clip_type, content, image_path, preview, timestamp, pinned = clip
            self._add_row(clip_id, clip_type, content, image_path, preview, timestamp, pinned)

    def _add_row(self, clip_id, clip_type, content, image_path, preview, timestamp, pinned):
        row = Adw.ActionRow()
        row.set_title(GLib.markup_escape_text((preview or "")[:60]))
        row.set_subtitle(timestamp)
        if pinned:
            row.add_css_class("accent")

        if clip_type == 'image' and image_path:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(image_path, 48, 48, True)
                row.add_prefix(Gtk.Image.new_from_pixbuf(pixbuf))
            except Exception:
                row.add_prefix(Gtk.Image.new_from_icon_name("image-x-generic"))
        else:
            row.add_prefix(Gtk.Image.new_from_icon_name("edit-paste-symbolic"))

        btn_box = Gtk.Box(spacing=4)
        btn_box.set_valign(Gtk.Align.CENTER)

        copy_btn = Gtk.Button()
        copy_btn.set_icon_name("edit-copy-symbolic")
        copy_btn.set_tooltip_text("Copy")
        copy_btn.add_css_class("flat")
        copy_btn.connect("clicked", self._on_copy, content, image_path, clip_type)
        btn_box.append(copy_btn)

        pin_btn = Gtk.Button()
        pin_btn.set_icon_name("view-pin-symbolic")
        pin_btn.set_tooltip_text("Unpin" if pinned else "Pin")
        pin_btn.add_css_class("flat")
        if pinned:
            pin_btn.add_css_class("accent")
        pin_btn.connect("clicked", self._on_pin, clip_id)
        btn_box.append(pin_btn)

        del_btn = Gtk.Button()
        del_btn.set_icon_name("edit-delete-symbolic")
        del_btn.set_tooltip_text("Delete")
        del_btn.add_css_class("flat")
        del_btn.add_css_class("destructive-action")
        del_btn.connect("clicked", self._on_delete, clip_id)
        btn_box.append(del_btn)

        row.add_suffix(btn_box)
        self.list_box.append(row)

    # ── Actions ──────────────────────────────────────────────────

    def _on_copy(self, btn, content, image_path, clip_type):
        clipboard = self.get_display().get_clipboard()
        if clip_type == 'text' and content:
            clipboard.set(content)
        elif clip_type == 'image' and image_path:
            try:
                clipboard.set(Gdk.Texture.new_from_filename(image_path))
            except Exception:
                pass

    def _on_pin(self, btn, clip_id):
        toggle_pin(clip_id)
        self._refresh()

    def _on_delete(self, btn, clip_id):
        delete_clip(clip_id)
        self._refresh()

    def _on_clear(self, btn):
        dialog = Adw.AlertDialog()
        dialog.set_heading("Clear History?")
        dialog.set_body("All unpinned clips will be deleted.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("clear", "Clear")
        dialog.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_clear_response)
        dialog.present(self)

    def _on_clear_response(self, dialog, response):
        if response == "clear":
            clear_all()
            self._refresh()
