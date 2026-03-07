# ClipVault 📋

A modern, native clipboard history manager for Linux built with GTK4 and libadwaita.

## Features

- 🔍 **Search** clipboard history instantly
- 🖼️ **Image support** — saves copied images too
- 📌 **Pin** important clips so they're never lost
- 🗑️ **Delete** individual clips or clear all at once
- 💾 Persistent history using SQLite
- 🎨 Native GTK4/libadwaita UI (follows your system theme)
- ✅ Wayland + X11 support

## Installation

### From Flathub (recommended)
```bash
flatpak install flathub io.github.clipvault
```

### From source
```bash
git clone https://github.com/rajnisht7/clipvault
cd clipvault
pip install .
clipvault
```

## Requirements

- Python 3.10+
- GTK 4
- libadwaita
- PyGObject

## Building Flatpak locally

```bash
flatpak install org.gnome.Platform//46 org.gnome.Sdk//46
flatpak-builder build-dir flatpak/io.github.clipvault.yml --force-clean
flatpak-builder --run build-dir flatpak/io.github.clipvault.yml clipvault
```

## License

GPL-3.0-or-later
