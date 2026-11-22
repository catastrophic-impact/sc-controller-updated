"""Profile import / export round trips (scc.profile_package). Uses a throwaway config folder."""

import io
import json
import os
import tarfile
import tempfile
import unittest

BASE = {
	"_": "",
	"buttons": {},
	"cpad": {},
	"gyro": {},
	"is_template": False,
	"lstick": {"action": "XY(axis(ABS_X), axis(ABS_Y))"},
	"menus": {},
	"pad_left": {},
	"pad_right": {},
	"rstick": {},
	"trigger_left": {},
	"trigger_right": {},
	"version": 1.4,
}


def profile_json(**buttons):
	d = json.loads(json.dumps(BASE))
	d["buttons"] = {k: {"action": v} for k, v in buttons.items()}
	return json.dumps(d, indent=4)


class PackageTest(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.cfg = os.path.join(self.tmp.name, "cfg")
		os.environ["XDG_CONFIG_HOME"] = self.cfg
		from scc import profile_package as pp
		from scc.paths import get_menus_path, get_profiles_path

		self.pp = pp
		os.makedirs(get_profiles_path(), exist_ok=True)
		os.makedirs(get_menus_path(), exist_ok=True)
		self.profiles, self.menus = get_profiles_path(), get_menus_path()

	def put(self, folder, name, text):
		with open(os.path.join(folder, name), "w") as f:
			f.write(text)

	def load(self, text):
		from scc.parser import ActionParser
		from scc.profile import Profile

		return Profile(ActionParser()).load_fileobj(io.StringIO(text))

	def other_config(self):
		"""Switch to an empty config folder (a second machine)."""
		other = os.path.join(self.tmp.name, "other")
		os.environ["XDG_CONFIG_HOME"] = other
		from scc.paths import get_menus_path, get_profiles_path

		os.makedirs(get_profiles_path(), exist_ok=True)
		os.makedirs(get_menus_path(), exist_ok=True)
		return get_profiles_path(), get_menus_path()

	def make_bundle_source(self):
		self.put(self.profiles, "Second.sccprofile", profile_json(X="button(Keys.KEY_X)"))
		self.put(self.menus, "Mine.menu", json.dumps([{"action": "button(Keys.KEY_A)", "id": "i1", "name": "A"}]))
		return profile_json(A="profile('Second')", B="menu('Mine.menu')", Y="button(Keys.KEY_Y)")

	def test_plain_roundtrip(self):
		text = profile_json(A="button(Keys.KEY_ENTER)", B="button(Keys.KEY_ESC)")
		prof = self.load(text)
		self.assertFalse(self.pp.needs_bundle(prof))
		out = os.path.join(self.tmp.name, "Plain.sccprofile")
		info = self.pp.export_profile(prof, "Plain", out)
		self.assertFalse(info["bundled"])
		self.assertFalse(tarfile.is_tarfile(out))
		self.other_config()
		pkg = self.pp.plan(self.pp.read_package(out))
		self.assertEqual(self.pp.apply(pkg), "Plain")
		from scc.paths import get_profiles_path

		saved = self.load(open(os.path.join(get_profiles_path(), "Plain.sccprofile")).read())
		self.assertEqual(self.pp.profile_text(saved), self.pp.profile_text(prof))

	def test_export_uses_live_unsaved_state(self):
		prof = self.load(profile_json(A="button(Keys.KEY_ENTER)"))
		prof.buttons  # noqa: B018
		text = self.pp.profile_text(prof)
		self.assertIn("KEY_ENTER", text)

	def test_bundle_roundtrip(self):
		prof = self.load(self.make_bundle_source())
		self.assertTrue(self.pp.needs_bundle(prof))
		out = os.path.join(self.tmp.name, "Main.sccprofile.tar.gz")
		info = self.pp.export_profile(prof, "Main", out, controller="sc")
		self.assertTrue(info["bundled"])
		with tarfile.open(out) as t:
			names = sorted(t.getnames())
		self.assertEqual(names, ["Main.sccprofile", "Mine.menu", "Second.sccprofile", "profile-name", "scc-export.json"])
		profiles, menus = self.other_config()
		pkg = self.pp.read_package(out)
		self.assertEqual(pkg.meta["controller"], "sc")
		self.assertEqual(pkg.main.name, "Main")
		self.assertEqual(self.pp.apply(self.pp.plan(pkg)), "Main")
		self.assertEqual(sorted(os.listdir(profiles)), ["Main.sccprofile", "Second.sccprofile"])
		self.assertEqual(os.listdir(menus), ["Mine.menu"])
		main = self.load(open(os.path.join(profiles, "Main.sccprofile")).read())
		self.assertIn("Second", self.pp.profile_text(main))

	def test_second_import_reuses_identical_extras_and_copies_main(self):
		prof = self.load(self.make_bundle_source())
		out = os.path.join(self.tmp.name, "m.tar.gz")
		self.pp.export_profile(prof, "Main", out)
		profiles, menus = self.other_config()
		self.pp.apply(self.pp.plan(self.pp.read_package(out)))
		pkg = self.pp.plan(self.pp.read_package(out))
		self.assertEqual(pkg.main.new_name, "Main (2)")
		self.assertEqual({i.name: i.action for i in pkg.extras}, {"Second": "reuse", "Mine.menu": "reuse"})
		self.pp.apply(pkg)
		self.assertEqual(sorted(os.listdir(profiles)), ["Main (2).sccprofile", "Main.sccprofile", "Second.sccprofile"])
		self.assertEqual(os.listdir(menus), ["Mine.menu"])

	def test_changed_extra_is_imported_under_new_name_and_references_follow(self):
		prof = self.load(self.make_bundle_source())
		out = os.path.join(self.tmp.name, "m.tar.gz")
		self.pp.export_profile(prof, "Main", out)
		profiles, menus = self.other_config()
		self.put(profiles, "Second.sccprofile", profile_json(X="button(Keys.KEY_Z)"))  # different Second already exists
		before = open(os.path.join(profiles, "Second.sccprofile")).read()
		self.assertEqual(self.pp.apply(self.pp.plan(self.pp.read_package(out))), "Main")
		self.assertEqual(open(os.path.join(profiles, "Second.sccprofile")).read(), before)  # untouched
		self.assertTrue(os.path.exists(os.path.join(profiles, "Second (2).sccprofile")))
		main = open(os.path.join(profiles, "Main.sccprofile")).read()
		self.assertIn("Second (2)", main)

	def test_replace_overwrites_only_when_asked(self):
		self.put(self.profiles, "Same.sccprofile", profile_json(A="button(Keys.KEY_A)"))
		prof = self.load(profile_json(A="button(Keys.KEY_B)"))
		out = os.path.join(self.tmp.name, "Same.sccprofile")
		self.pp.export_profile(prof, "Same", out)
		pkg = self.pp.read_package(out)
		self.assertEqual([i.name for i in self.pp.conflicts(pkg)], ["Same"])
		self.assertEqual(self.pp.apply(self.pp.plan(pkg)), "Same (2)")  # default is a copy
		self.assertIn("KEY_A", open(os.path.join(self.profiles, "Same.sccprofile")).read())
		pkg = self.pp.plan(self.pp.read_package(out), main_action="replace")
		self.assertEqual(self.pp.apply(pkg), "Same")
		self.assertIn("KEY_B", open(os.path.join(self.profiles, "Same.sccprofile")).read())

	def test_builtin_profile_is_never_replaced(self):
		prof = self.load(profile_json(A="button(Keys.KEY_B)"))
		out = os.path.join(self.tmp.name, "Desktop.sccprofile")
		self.pp.export_profile(prof, "Desktop", out)
		pkg = self.pp.plan(self.pp.read_package(out), main_action="replace")
		self.assertEqual(pkg.main.new_name, "Desktop (2)")

	def test_shell_commands_are_reported(self):
		out = os.path.join(self.tmp.name, "Sh.sccprofile")
		self.put(self.tmp.name, "Sh.sccprofile", profile_json(A="shell('echo hi')"))
		self.assertEqual(self.pp.shell_commands(self.pp.read_package(out)), ["echo hi"])
		self.put(self.tmp.name, "Ok.sccprofile", profile_json(A="button(Keys.KEY_A)"))
		self.assertEqual(self.pp.shell_commands(self.pp.read_package(os.path.join(self.tmp.name, "Ok.sccprofile"))), [])

	def test_bad_files_give_readable_errors(self):
		bad = os.path.join(self.tmp.name, "bad.sccprofile")
		self.put(self.tmp.name, "bad.sccprofile", "not json at all")
		with self.assertRaises(self.pp.PackageError):
			self.pp.read_package(bad)

	def test_tar_with_path_tricks_is_contained(self):
		out = os.path.join(self.tmp.name, "evil.tar.gz")
		with tarfile.open(out, "w:gz") as t:
			for arc, text in (
				("Good.sccprofile", profile_json(A="button(Keys.KEY_A)")),
				("profile-name", "Good"),
				("../escape.sccprofile", profile_json()),
				("sub/dir.menu", "[]"),
			):
				data = text.encode()
				info = tarfile.TarInfo(arc)
				info.size = len(data)
				t.addfile(info, io.BytesIO(data))
		pkg = self.pp.read_package(out)
		self.assertEqual(pkg.extras, [])
		self.pp.apply(self.pp.plan(pkg))
		self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "escape.sccprofile")))

	def test_valid_name(self):
		for bad in ("", ".hidden", "a/b", "a\\b", " pad"):
			self.assertFalse(self.pp.valid_name(bad), bad)
		self.assertTrue(self.pp.valid_name("My profile (2)"))


if __name__ == "__main__":
	unittest.main()
