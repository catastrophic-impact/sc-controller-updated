"""SC-Controller - controller access setup (fork).

Linux only lets programs talk to a Steam controller and create a virtual keyboard / mouse when udev rules allow it.
That needs administrator rights, so the app cannot do it silently: this window checks what is blocked and gives the
user one command to copy and run in a terminal.
"""

from __future__ import annotations

import glob
import logging
import os
import sys

from gi.repository import Gdk, GLib, Gtk

from scc.tools import _

log = logging.getLogger("Permissions")

VALVE = "28de"
RULES_NAME = "69-sc-controller.rules"
MARKER = "SCC_RULES"


def rules_text() -> str:
	"""The udev rules shipped with the app (inside the AppImage, or the source checkout)."""
	here = os.path.dirname(os.path.abspath(__file__))
	cands = []
	for base in (os.environ.get("APPDIR"), sys.prefix):
		if base:
			cands += [os.path.join(base, "usr/lib/udev/rules.d", RULES_NAME), os.path.join(base, "lib/udev/rules.d", RULES_NAME)]
	cands += [os.path.join(here, "..", "..", "scripts", RULES_NAME)]
	for c in cands:
		try:
			with open(c, encoding="utf-8") as f:
				return f.read().rstrip("\n")
		except OSError:
			continue
	return "# (rules file not found in this build)"


def install_command() -> str:
	"""One block that can be pasted into a terminal."""
	return (
		f"sudo tee /etc/udev/rules.d/{RULES_NAME} >/dev/null <<'{MARKER}'\n"
		f"{rules_text()}\n"
		f"{MARKER}\n"
		"echo uinput | sudo tee /etc/modules-load.d/uinput.conf >/dev/null\n"
		"sudo modprobe uinput\n"
		"sudo udevadm control --reload-rules && sudo udevadm trigger\n"
	)


def _sysattr(path: str) -> str:
	try:
		with open(path) as f:
			return f.read().strip()
	except OSError:
		return ""


def blocked_controller_devices() -> list[str]:
	"""Valve controller device nodes the current user cannot open for reading and writing."""
	blocked = []
	for dev in glob.glob("/sys/bus/usb/devices/*"):
		if _sysattr(os.path.join(dev, "idVendor")).lower() != VALVE:
			continue
		bus, num = _sysattr(os.path.join(dev, "busnum")), _sysattr(os.path.join(dev, "devnum"))
		if bus.isdigit() and num.isdigit():
			node = "/dev/bus/usb/%03d/%03d" % (int(bus), int(num))
			if os.path.exists(node) and not os.access(node, os.R_OK | os.W_OK):
				blocked.append(node)
	for h in glob.glob("/sys/class/hidraw/hidraw*"):
		uevent = _sysattr(os.path.join(h, "device", "uevent")).upper()
		if f"0000{VALVE.upper()}" in uevent:  # HID_ID=bus:vendor:product, vendor padded to 8 digits
			node = "/dev/" + os.path.basename(h)
			if os.path.exists(node) and not os.access(node, os.R_OK | os.W_OK):
				blocked.append(node)
	return blocked


def uinput_ok() -> bool:
	return os.path.exists("/dev/uinput") and os.access("/dev/uinput", os.W_OK)


def problems() -> list[str]:
	out = []
	if not uinput_ok():
		out.append("uinput")
	if blocked_controller_devices():
		out.append("controller")
	return out


class PermissionsDialog(Gtk.Window):
	def __init__(self, app) -> None:
		Gtk.Window.__init__(self, title=_("Set up controller access"), transient_for=app.window, modal=True)
		self.set_default_size(620, -1)
		box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
		for side in ("start", "end", "top", "bottom"):
			getattr(box, f"set_margin_{side}")(18)
		self.set_child(box)

		intro = Gtk.Label(xalign=0, wrap=True)
		intro.set_markup(
			"<b>%s</b>\n%s"
			% (
				GLib.markup_escape_text(_("A one-time step is needed")),
				GLib.markup_escape_text(
					_(
						"Linux must give this app permission to use your controller and to create a virtual keyboard and mouse. "
						"This needs administrator rights, so the app cannot do it for you. "
						"Copy the command below, paste it into a terminal and press Enter (it will ask for your password).",
					),
				),
			),
		)
		box.append(intro)

		self.status = Gtk.Label(xalign=0, wrap=True)
		box.append(self.status)

		self.text = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.NONE)
		self.text.get_buffer().set_text(install_command())
		scroll = Gtk.ScrolledWindow(min_content_height=180, vexpand=True)
		scroll.set_child(self.text)
		box.append(scroll)

		row = Gtk.Box(spacing=12, halign=Gtk.Align.END)
		self.recheck = Gtk.Button(label=_("Check again"))
		self.recheck.connect("clicked", lambda *a: self.refresh())
		self.copy = Gtk.Button(label=_("Copy command"))
		self.copy.add_css_class("suggested-action")
		self.copy.connect("clicked", self.on_copy)
		close = Gtk.Button(label=_("Close"))
		close.connect("clicked", lambda *a: self.close())
		for b in (self.recheck, close, self.copy):
			row.append(b)
		box.append(row)
		self.refresh()

	def refresh(self) -> None:
		probs = problems()
		ok, bad = "✔ ", "✘ "
		lines = [
			(bad if "uinput" in probs else ok) + _("Virtual keyboard / mouse (/dev/uinput): %s") % (_("blocked") if "uinput" in probs else _("OK")),
			(bad if "controller" in probs else ok)
			+ _("Controller access: %s") % (_("blocked") if "controller" in probs else _("OK (or no controller connected)")),
		]
		self.status.set_label("\n".join(lines))

	def on_copy(self, *a) -> None:
		buf = self.text.get_buffer()
		text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
		Gdk.Display.get_default().get_clipboard().set(text)
		self.copy.set_label(_("Copied ✔"))
		GLib.timeout_add_seconds(2, self._reset_copy)

	def _reset_copy(self):
		self.copy.set_label(_("Copy command"))
		return GLib.SOURCE_REMOVE
