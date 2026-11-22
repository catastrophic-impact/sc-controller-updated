"""GUI watchdog helper (scc.gui_watch)."""

import os
import subprocess
import sys
import time
import unittest


class GuiWatchTest(unittest.TestCase):
	def setUp(self):
		from scc import gui_watch

		self.gw = gui_watch

	def test_own_process_is_alive(self):
		self.assertTrue(self.gw.process_alive(os.getpid()))

	def test_bad_pids_are_not_alive(self):
		self.assertFalse(self.gw.process_alive(0))
		self.assertFalse(self.gw.process_alive(-5))
		self.assertFalse(self.gw.process_alive(2**22 + 12345))

	def test_running_child_alive_then_gone_after_exit(self):
		p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
		try:
			self.assertTrue(self.gw.process_alive(p.pid))
		finally:
			p.kill()
			p.wait()
		self.assertFalse(self.gw.process_alive(p.pid))

	def test_zombie_counts_as_gone(self):
		p = subprocess.Popen([sys.executable, "-c", "pass"])
		time.sleep(0.5)  # exited, but not reaped (no wait/poll yet) = zombie
		try:
			self.assertFalse(self.gw.process_alive(p.pid))
		finally:
			p.wait()

	def test_env_parsing(self):
		os.environ.pop(self.gw.GUI_PID_ENV, None)
		self.assertIsNone(self.gw.watched_gui_pid())
		os.environ[self.gw.GUI_PID_ENV] = "abc"
		self.assertIsNone(self.gw.watched_gui_pid())
		os.environ[self.gw.GUI_PID_ENV] = "4242"
		self.assertEqual(self.gw.watched_gui_pid(), 4242)
		os.environ.pop(self.gw.GUI_PID_ENV, None)


if __name__ == "__main__":
	unittest.main()
