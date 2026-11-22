"""SC-Controller - profile packages (fork).

Import / export of profiles without any GUI code, so it can be tested.

A package is either
  * a plain ``.sccprofile`` file (profile that references nothing else), or
  * a ``.sccprofile.tar.gz`` holding the profile plus the profiles and menus it references,
    ``profile-name`` (name of the main profile) and ``scc-export.json`` (metadata).

Importing never overwrites anything silently: the caller gets a list of conflicts and decides per item.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import tarfile
from dataclasses import dataclass, field

from scc.menu_data import MenuData, Submenu
from scc.parser import ActionParser
from scc.profile import Encoder, Profile
from scc.special_actions import ChangeProfileAction, MenuAction, ShellCommandAction
from scc.tools import (
	find_menu,
	find_profile,
	get_menus_path,
	get_profiles_path,
	menu_is_default,
	profile_is_default,
)

log = logging.getLogger("ProfilePackage")

FORMAT = 1
META_NAME = "scc-export.json"
MAIN_NAME = "profile-name"
MAX_MEMBER_BYTES = 5 * 1024 * 1024
MAX_MEMBERS = 200

PROFILE = "profile"
MENU = "menu"


class PackageError(Exception):
	"""File cannot be read as a profile package. Message is fit to show to the user."""


@dataclass
class Item:
	kind: str  # PROFILE or MENU
	name: str  # profile name (no extension) or menu file name (with .menu)
	text: str  # file content
	new_name: str = ""  # name it will be saved under (set by plan)
	action: str = "copy"  # copy | replace | skip | reuse


@dataclass
class Package:
	main: Item
	extras: list[Item] = field(default_factory=list)
	meta: dict = field(default_factory=dict)

	def all_items(self) -> list[Item]:
		return [self.main, *self.extras]


# ---------------------------------------------------------------- names


def valid_name(name: str) -> bool:
	"""Profile names end up in file names: no path parts, no leading dot, not empty."""
	return bool(name) and name == name.strip() and not name.startswith(".") and re.fullmatch(r"[^/\\\0]+", name) is not None


def _file_name(kind: str, name: str) -> str:
	return f"{name}.sccprofile" if kind == PROFILE else name


def _target_dir(kind: str) -> str:
	return get_profiles_path() if kind == PROFILE else get_menus_path()


def _find(kind: str, name: str) -> str | None:
	return find_profile(name) if kind == PROFILE else find_menu(name)


def _is_default(kind: str, name: str) -> bool:
	return profile_is_default(name) if kind == PROFILE else menu_is_default(name)


def free_name(kind: str, name: str, taken: set[str] = frozenset()) -> str:
	"""'Name' -> 'Name (2)', 'Name (3)'... first one that is not used by an existing file or by `taken`."""
	if kind == MENU:
		base, ext = (name[:-5], ".menu") if name.endswith(".menu") else (name, "")
	else:
		base, ext = name, ""
	n = 2
	while True:
		cand = f"{base} ({n}){ext}"
		if _find(kind, cand) is None and cand not in taken:
			return cand
		n += 1


# ------------------------------------------------------------ references


def _walk_actions(profile: Profile):
	"""Every action of a profile, including actions of its inline menus."""
	yield from profile.get_all_actions()
	for menu in profile.menus.values():
		for item in menu:
			if hasattr(item, "action") and item.action is not None:
				yield from _flatten(item.action)


def _flatten(action):
	yield action
	if hasattr(action, "get_all_actions"):
		try:
			yield from action.get_all_actions()
		except Exception:  # noqa: BLE001 - odd actions must not break export
			pass


def references(profile: Profile) -> tuple[list[Item], list[str]]:
	"""Profiles and menu files `profile` needs (recursively), as Items with text, plus names that cannot be found.

	Built-in profiles / menus are not included: every install has them.
	"""
	items: list[Item] = []
	missing: list[str] = []
	seen: set[tuple[str, str]] = set()

	def add_profile(name: str) -> None:
		if (PROFILE, name) in seen:
			return
		seen.add((PROFILE, name))
		if profile_is_default(name) and find_profile(name) and not _user_has(PROFILE, name):
			return
		path = find_profile(name)
		if not path:
			missing.append(_("profile") + ": " + name)
			return
		try:
			text = _read(path)
			sub = Profile(ActionParser()).load_fileobj(io.StringIO(text))
		except Exception as e:  # noqa: BLE001
			missing.append(f"profile: {name} ({e})")
			return
		items.append(Item(PROFILE, name, text))
		scan(sub)

	def add_menu(menu_id: str) -> None:
		if "." not in menu_id or (MENU, menu_id) in seen:
			return
		seen.add((MENU, menu_id))
		if menu_is_default(menu_id) and not _user_has(MENU, menu_id):
			return
		path = find_menu(menu_id)
		if not path:
			missing.append(_("menu") + ": " + menu_id)
			return
		try:
			text = _read(path)
			menu = MenuData.from_json_data(json.loads(text), ActionParser())
		except Exception as e:  # noqa: BLE001
			missing.append(f"menu: {menu_id} ({e})")
			return
		items.append(Item(MENU, menu_id, text))
		scan_menu(menu)

	def scan_menu(menu) -> None:
		for item in menu:
			if isinstance(item, Submenu):
				add_menu(os.path.split(item.filename)[-1])
			if getattr(item, "action", None) is not None:
				for a in _flatten(item.action):
					look(a)

	def look(a) -> None:
		if isinstance(a, ChangeProfileAction):
			add_profile(a.profile)
		elif isinstance(a, MenuAction):
			add_menu(a.menu_id)

	def scan(p: Profile) -> None:
		for a in _walk_actions(p):
			look(a)
		for m in p.menus.values():
			scan_menu(m)

	scan(profile)
	return items, missing


def _user_has(kind: str, name: str) -> bool:
	"""True if the user folder holds a file with this name (overriding a built-in one)."""
	return os.path.exists(os.path.join(_target_dir(kind), _file_name(kind, name)))


def _read(path: str) -> str:
	with open(path, encoding="utf-8") as f:
		return f.read()


def _(text: str) -> str:
	return text


# ---------------------------------------------------------------- export


def profile_text(profile: Profile) -> str:
	buf = io.StringIO()
	profile.save_fileobj(buf)
	return buf.getvalue()


def needs_bundle(profile: Profile) -> bool:
	items, _missing = references(profile)
	return bool(items)


def export_profile(profile: Profile, name: str, target: str, controller: str = "") -> dict:
	"""Writes `profile` (the live, possibly unsaved state) to `target`.

	Plain JSON file when nothing else is referenced, otherwise a tar.gz bundle with the referenced profiles and menus.
	Returns {"bundled": bool, "files": [...], "missing": [...]}.
	"""
	items, missing = references(profile)
	text = profile_text(profile)
	if not items:
		with open(target, "w", encoding="utf-8") as f:
			f.write(text)
		return {"bundled": False, "files": [], "missing": missing}

	meta = {"format": FORMAT, "name": name, "controller": controller}
	with tarfile.open(target, "w:gz") as tar:
		_add(tar, f"{name}.sccprofile", text)
		for it in items:
			_add(tar, _file_name(it.kind, it.name), it.text)
		_add(tar, MAIN_NAME, name)
		_add(tar, META_NAME, json.dumps(meta, indent=2))
	return {"bundled": True, "files": [_file_name(i.kind, i.name) for i in items], "missing": missing}


def _add(tar: tarfile.TarFile, arcname: str, text: str) -> None:
	data = text.encode("utf-8")
	info = tarfile.TarInfo(arcname)
	info.size = len(data)
	info.mode = 0o644
	tar.addfile(info, io.BytesIO(data))


# ---------------------------------------------------------------- import


def read_package(path: str) -> Package:
	"""Reads a plain profile or a bundle. Raises PackageError with a readable message."""
	try:
		if tarfile.is_tarfile(path):
			return _read_tar(path)
		return _read_plain(path)
	except PackageError:
		raise
	except Exception as e:  # noqa: BLE001
		raise PackageError(f"This file is not a valid profile ({e}).") from e


def _check_profile(text: str) -> None:
	Profile(ActionParser()).load_fileobj(io.StringIO(text))


def _check_menu(text: str) -> None:
	MenuData.from_json_data(json.loads(text), ActionParser())


def _read_plain(path: str) -> Package:
	text = _read(path)
	_check_profile(text)
	name = os.path.basename(path)
	for ext in (".sccprofile.mod", ".sccprofile", ".json"):
		if name.endswith(ext):
			name = name[: -len(ext)]
			break
	if not valid_name(name):
		name = "Imported profile"
	return Package(Item(PROFILE, name, text), [], {"format": FORMAT})


def _read_tar(path: str) -> Package:
	with tarfile.open(path, "r:*") as tar:
		members = tar.getmembers()
		if len(members) > MAX_MEMBERS:
			raise PackageError("This package contains too many files.")
		files: dict[str, str] = {}
		for m in members:
			if not m.isfile() or m.size > MAX_MEMBER_BYTES or "/" in m.name or "\\" in m.name or m.name.startswith("."):
				continue  # ignore anything that is not a plain, small file in the root of the archive
			fo = tar.extractfile(m)
			if fo is None:
				continue
			with fo:
				files[m.name] = fo.read().decode("utf-8")
	meta: dict = {}
	if META_NAME in files:
		try:
			meta = json.loads(files[META_NAME])
		except ValueError:
			meta = {}
	main_name = files.get(MAIN_NAME, "").strip()
	if not main_name:
		cands = [n[:-11] for n in files if n.endswith(".sccprofile")]
		if len(cands) != 1:
			raise PackageError("This package does not say which profile is the main one.")
		main_name = cands[0]
	if f"{main_name}.sccprofile" not in files or not valid_name(main_name):
		raise PackageError("The main profile is missing from this package.")
	_check_profile(files[f"{main_name}.sccprofile"])
	main = Item(PROFILE, main_name, files[f"{main_name}.sccprofile"])
	extras: list[Item] = []
	for fname, text in files.items():
		if fname.endswith(".sccprofile") and fname != f"{main_name}.sccprofile":
			_check_profile(text)
			extras.append(Item(PROFILE, fname[:-11], text))
		elif fname.endswith(".menu"):
			_check_menu(text)
			extras.append(Item(MENU, fname, text))
	return Package(main, extras, meta)


def shell_commands(package: Package) -> list[str]:
	"""Every shell() command the package would install. The user has to approve these."""
	out: list[str] = []
	for it in package.all_items():
		if it.kind == PROFILE:
			p = Profile(ActionParser()).load_fileobj(io.StringIO(it.text))
			out += [a.command for a in _walk_actions(p) if isinstance(a, ShellCommandAction)]
		else:
			m = MenuData.from_json_data(json.loads(it.text), ActionParser())
			for item in m:
				if getattr(item, "action", None) is not None:
					out += [a.command for a in _flatten(item.action) if isinstance(a, ShellCommandAction)]
	return out


def plan(package: Package, main_name: str | None = None, main_action: str | None = None) -> Package:
	"""Decides what happens to every item and fills in `new_name` / `action`.

	Main profile: the caller's choice, else a free copy name if the name is taken. Extras never replace anything:
	identical content is reused, different content is imported under a free name (references get rewritten).
	"""
	taken: set[str] = set()
	main = package.main
	main.new_name = main_name or main.name
	existing = _find(PROFILE, main.new_name)
	if main_action:
		main.action = main_action
	else:
		main.action = "copy"
	if main.action == "copy" and (existing or main.new_name in taken):
		main.new_name = free_name(PROFILE, main.new_name)
	if main.action == "replace" and existing and _is_default(PROFILE, main.new_name) and not _user_has(PROFILE, main.new_name):
		main.action = "copy"  # built-in profiles are never replaced
		main.new_name = free_name(PROFILE, main.new_name)
	taken.add(main.new_name)

	for it in package.extras:
		path = _find(it.kind, it.name)
		if path is None:
			it.new_name, it.action = it.name, "copy"
		elif _same(it.kind, _read(path), it.text):
			it.new_name, it.action = it.name, "reuse"
		else:
			it.new_name, it.action = free_name(it.kind, it.name, taken), "copy"
		taken.add(it.new_name)
	return package


def _normalized(kind: str, text: str) -> str:
	"""Canonical text of a profile / menu, so formatting differences do not count as changes."""
	if kind == PROFILE:
		return profile_text(Profile(ActionParser()).load_fileobj(io.StringIO(text)))
	return Encoder(sort_keys=True, indent=4).encode(MenuData.from_json_data(json.loads(text), ActionParser()))


def _same(kind: str, a: str, b: str) -> bool:
	try:
		return json.loads(_normalized(kind, a)) == json.loads(_normalized(kind, b))
	except Exception:  # noqa: BLE001
		return a == b


def conflicts(package: Package) -> list[Item]:
	"""Items whose name is already used (before planning)."""
	return [i for i in package.all_items() if _find(i.kind, i.name)]


def apply(package: Package) -> str:
	"""Writes a planned package to the user's folders. Returns the name the main profile was saved as."""
	prof_map = {i.name: i.new_name for i in package.all_items() if i.kind == PROFILE and i.action in ("copy", "replace")}
	menu_map = {i.name: i.new_name for i in package.all_items() if i.kind == MENU and i.action in ("copy", "replace")}
	os.makedirs(get_profiles_path(), exist_ok=True)
	os.makedirs(get_menus_path(), exist_ok=True)

	def rewrite(actions) -> None:
		for a in actions:
			if isinstance(a, ChangeProfileAction) and a.profile in prof_map and prof_map[a.profile] != a.profile:
				a.profile = prof_map[a.profile]
				a.parameters = tuple([a.profile] + list(a.parameters[1:]))
			elif isinstance(a, MenuAction) and a.menu_id in menu_map and menu_map[a.menu_id] != a.menu_id:
				a.menu_id = menu_map[a.menu_id]
				a.parameters = tuple([a.menu_id] + list(a.parameters[1:]))

	for it in package.all_items():
		if it.action not in ("copy", "replace"):
			continue
		dest = os.path.join(_target_dir(it.kind), _file_name(it.kind, it.new_name))
		if it.kind == PROFILE:
			p = Profile(ActionParser()).load_fileobj(io.StringIO(it.text))
			rewrite(_walk_actions(p))
			for m in p.menus.values():
				rewrite(a for i in m if getattr(i, "action", None) is not None for a in _flatten(i.action))
				for i in m:
					if isinstance(i, Submenu) and os.path.split(i.filename)[-1] in menu_map:
						i.filename = menu_map[os.path.split(i.filename)[-1]]
			_write(dest, profile_text(p))
		else:
			m = MenuData.from_json_data(json.loads(it.text), ActionParser())
			rewrite(a for i in m if getattr(i, "action", None) is not None for a in _flatten(i.action))
			for i in m:
				if isinstance(i, Submenu) and os.path.split(i.filename)[-1] in menu_map:
					i.filename = menu_map[os.path.split(i.filename)[-1]]
			_write(dest, Encoder(sort_keys=True, indent=4).encode(m))
	return package.main.new_name


def _write(path: str, text: str) -> None:
	tmp = path + ".tmp"
	with open(tmp, "w", encoding="utf-8") as f:
		f.write(text)
	os.replace(tmp, path)
