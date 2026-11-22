"""SC-Controller - simple profile Import / Export dialogs (fork).

Export: one click - pick where to save, everything the profile needs is bundled quietly.
Import: pick a file, see what it contains, choose a name (and what to do on a name clash), confirm.
All the logic lives in scc.profile_package (GUI-free and tested); this file is only windows.
"""

from __future__ import annotations

import logging
import os

from gi.repository import Gio, GLib, Gtk

from scc import profile_package as pp
from scc.gui.parser import GuiActionParser
from scc.profile import Profile
from scc.tools import _, get_profiles_path

log = logging.getLogger("ProfileIO")

CONTROLLER_NAMES = {"deck": _("Steam Deck"), "sc": _("Steam Controller")}


def controller_kind(app) -> str:
	"""'deck', 'sc' or '' for the controller currently being edited."""
	c = app.profile_switchers[0].get_controller()
	cid = c.get_id() if c else ""
	return "deck" if cid.startswith("deck") else "sc" if cid.startswith("sc") else ""


def message(app, text: str, detail: str = "") -> None:
	dlg = Gtk.AlertDialog()
	dlg.set_message(text)
	if detail:
		dlg.set_detail(detail)
	dlg.show(app.window)


def _filters(*patterns) -> Gio.ListStore:
	store = Gio.ListStore.new(Gtk.FileFilter)
	flt = Gtk.FileFilter()
	flt.set_name(_("SC-Controller profiles"))
	for p in patterns:
		flt.add_pattern(p)
	store.append(flt)
	return store


# ---------------------------------------------------------------- export


def export_profile(app) -> None:
	name = app.profile_switchers[0].get_profile_name() or _("profile")
	try:
		bundled = pp.needs_bundle(app.current)
	except Exception as e:  # noqa: BLE001
		log.error("Export check failed: %s", e)
		bundled = False
	ext = ".sccprofile.tar.gz" if bundled else ".sccprofile"
	dlg = Gtk.FileDialog()
	dlg.set_title(_("Export profile"))
	dlg.set_accept_label(_("Export"))
	dlg.set_initial_name(name + ext)
	dlg.set_filters(_filters("*.sccprofile", "*.tar.gz"))

	def done(d, res) -> None:
		try:
			path = d.save_finish(res).get_path()
		except GLib.Error:
			return  # cancelled
		if bundled and not path.endswith(".tar.gz"):
			path += ".tar.gz"
		elif not bundled and not path.endswith(".sccprofile"):
			path += ".sccprofile"
		try:
			info = pp.export_profile(app.current, name, path, controller_kind(app))
		except Exception as e:  # noqa: BLE001
			log.error("Export failed: %s", e)
			message(app, _("Could not export the profile."), str(e))
			return
		if info["missing"]:
			message(
				app,
				_("Profile exported, but some things it uses could not be found:"),
				"\n".join(info["missing"]),
			)

	dlg.save(app.window, None, done)


# ---------------------------------------------------------------- import


def import_profile(app) -> None:
	dlg = Gtk.FileDialog()
	dlg.set_title(_("Import profile"))
	dlg.set_accept_label(_("Open"))
	dlg.set_filters(_filters("*.sccprofile", "*.tar.gz", "*.tgz", "*.json"))

	def done(d, res) -> None:
		try:
			path = d.open_finish(res).get_path()
		except GLib.Error:
			return  # cancelled
		try:
			package = pp.read_package(path)
		except pp.PackageError as e:
			message(app, _("Could not import this file."), str(e))
			return
		ImportPreview(app, package).present()

	dlg.open(app.window, None, done)


class ImportPreview(Gtk.Window):
	"""What is in the file, what it will be called, what happens on a name clash - then Import."""

	def __init__(self, app, package: pp.Package) -> None:
		Gtk.Window.__init__(self, title=_("Import profile"), transient_for=app.window, modal=True)
		self.set_default_size(460, -1)
		self.app, self.package = app, package
		self.original = package.main.name
		self.clash = pp._find(pp.PROFILE, self.original) is not None
		# Replacing is only offered for the user's own profiles, never for built-in ones
		self.can_replace = self.clash and (not pp._is_default(pp.PROFILE, self.original) or pp._user_has(pp.PROFILE, self.original))

		box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
		for side in ("start", "end", "top", "bottom"):
			getattr(box, f"set_margin_{side}")(18)
		self.set_child(box)

		head = Gtk.Label(xalign=0, wrap=True)
		head.set_markup("<b>%s</b>" % GLib.markup_escape_text(_("Import this profile?")))
		box.append(head)

		row = Gtk.Box(spacing=12)
		row.append(Gtk.Label(label=_("Name:"), xalign=0))
		self.entry = Gtk.Entry(hexpand=True, text=self.original)
		self.entry.connect("changed", self.refresh)
		row.append(self.entry)
		box.append(row)

		self.mode = Gtk.DropDown.new_from_strings([_("Import as a new profile"), _("Replace the existing profile")])
		self.mode.connect("notify::selected", self.on_mode)
		self.mode.set_visible(self.can_replace)
		box.append(self.mode)

		self.hint = Gtk.Label(xalign=0, wrap=True)
		box.append(self.hint)

		self.extras = Gtk.Label(xalign=0, wrap=True)
		box.append(self.extras)

		self.controller_note = Gtk.Label(xalign=0, wrap=True)
		box.append(self.controller_note)

		self.shells = pp.shell_commands(package)
		self.trust = Gtk.CheckButton(label=_("I trust this profile and allow it to run these commands"))
		self.trust.connect("toggled", self.refresh)
		self.shell_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		warn = Gtk.Label(xalign=0, wrap=True, selectable=True)
		warn.set_markup(
			"<b>%s</b>\n%s"
			% (
				GLib.markup_escape_text(_("This profile runs commands on your computer:")),
				GLib.markup_escape_text("\n".join(self.shells)),
			),
		)
		self.shell_box.append(warn)
		self.shell_box.append(self.trust)
		self.shell_box.set_visible(bool(self.shells))
		box.append(self.shell_box)

		buttons = Gtk.Box(spacing=12, halign=Gtk.Align.END)
		cancel = Gtk.Button(label=_("Cancel"))
		cancel.connect("clicked", lambda *a: self.close())
		self.ok = Gtk.Button(label=_("Import"))
		self.ok.add_css_class("suggested-action")
		self.ok.connect("clicked", self.on_import)
		buttons.append(cancel)
		buttons.append(self.ok)
		box.append(buttons)

		if self.clash:
			self.entry.set_text(pp.free_name(pp.PROFILE, self.original))
		self.refresh()

	def on_mode(self, *a) -> None:
		replace = self.mode.get_selected() == 1
		self.entry.set_sensitive(not replace)
		self.entry.set_text(self.original if replace else pp.free_name(pp.PROFILE, self.original))
		self.refresh()

	def chosen(self) -> tuple[str, str]:
		name = self.entry.get_text().strip()
		action = "replace" if (self.can_replace and self.mode.get_selected() == 1) else "copy"
		return name, action

	def refresh(self, *a) -> None:
		name, action = self.chosen()
		ok = pp.valid_name(name)
		if not ok:
			self.hint.set_label(_("Please enter a name (it cannot contain / or start with a dot)."))
		elif action == "replace":
			self.hint.set_label(_("The existing profile “%s” will be overwritten.") % name)
		elif pp._find(pp.PROFILE, name):
			self.hint.set_label(
				_("A profile named “%s” already exists. This one will be saved as “%s”.") % (name, pp.free_name(pp.PROFILE, name)),
			)
		else:
			self.hint.set_label("")

		if ok:
			planned = pp.plan(self.package, name, action)
			lines = []
			for it in planned.extras:
				kind = _("Profile") if it.kind == pp.PROFILE else _("Menu")
				shown = it.name[:-5] if it.kind == pp.MENU else it.name
				if it.action == "reuse":
					lines.append(_("%s “%s”: already installed, will be used as it is") % (kind, shown))
				elif it.new_name != it.name:
					lines.append(_("%s “%s”: a different one exists, will be added as “%s”") % (kind, shown, it.new_name))
				else:
					lines.append(_("%s “%s”: will be added") % (kind, shown))
			self.extras.set_label(_("Also included:") + "\n" + "\n".join(lines) if lines else "")
		self.extras.set_visible(bool(self.package.extras) and ok)

		made_for, mine = self.package.meta.get("controller", ""), controller_kind(self.app)
		if made_for and mine and made_for != mine:
			self.controller_note.set_label(
				_("Note: this profile was made for a %s, you are editing a %s. Buttons it uses may not exist there.")
				% (CONTROLLER_NAMES.get(made_for, made_for), CONTROLLER_NAMES.get(mine, mine)),
			)
		self.controller_note.set_visible(bool(self.controller_note.get_label()))
		self.ok.set_sensitive(ok and (not self.shells or self.trust.get_active()))

	def on_import(self, *a) -> None:
		name, action = self.chosen()
		try:
			final = pp.apply(pp.plan(self.package, name, action))
			profile = Profile(GuiActionParser()).load(os.path.join(get_profiles_path(), f"{final}.sccprofile"))
		except Exception as e:  # noqa: BLE001
			log.error("Import failed: %s", e)
			message(self.app, _("Import failed."), str(e))
			return
		self.close()
		self.app.new_profile(profile, final)
