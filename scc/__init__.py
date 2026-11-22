"""SC-Controller.

Copyright (C) 2018 Kozec

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License version 2 as published by
the Free Software Foundation

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""

import os
import subprocess

# fork: set before GTK is ever loaded. Software rendering avoids the "Failed to realize renderer ... EGL / Vulkan"
# messages inside the AppImage (no GPU driver is reachable there, GTK fell back to this anyway). Dark theme is permanent.
# Portable mode: when running as an AppImage, ALL settings/data/cache live in a "config" folder next to the .AppImage
# file (never ~/.config). SCC_CONFIG_DIR overrides the location. Applies to the GUI and the daemon (it inherits this).
_portable = os.environ.get("SCC_CONFIG_DIR") or (
	os.path.join(os.path.dirname(os.path.abspath(os.environ["APPIMAGE"])), "config") if os.environ.get("APPIMAGE") else None
)
if _portable:
	os.environ["XDG_CONFIG_HOME"] = _portable
	os.environ["XDG_DATA_HOME"] = os.path.join(_portable, "data")
	os.environ["XDG_CACHE_HOME"] = os.path.join(_portable, "cache")
	for _d in (_portable, os.environ["XDG_DATA_HOME"], os.environ["XDG_CACHE_HOME"]):
		os.makedirs(_d, exist_ok=True)
os.environ.setdefault("GSK_RENDERER", "cairo")
os.environ.setdefault("GTK_THEME", "Adwaita:dark")

# AppImageBuilder relies on its exec hooks to resolve relative shebang and ELF
# interpreter paths. Python 3.13+ uses posix_spawn() in more situations, which
# bypasses that compatibility path.
if os.environ.get("APPDIR") and hasattr(subprocess, "_USE_POSIX_SPAWN"):
	subprocess._USE_POSIX_SPAWN = False
