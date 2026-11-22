"""SC-Controller - GUI watchdog helper (fork).

The GUI tells the daemon it started (SCC_GUI_PID). If the GUI dies without stopping the daemon (crash, kill), the daemon
notices and shuts itself down so the controller returns to normal.
"""

import os

GUI_PID_ENV = "SCC_GUI_PID"
CHECK_SECONDS = 3


def process_alive(pid: int) -> bool:
	"""True if `pid` is a running process. A zombie (dead, not yet reaped by its parent) counts as gone."""
	if pid <= 0:
		return False
	try:
		os.kill(pid, 0)
	except ProcessLookupError:
		return False
	except PermissionError:
		return True  # exists, belongs to someone else
	try:
		with open(f"/proc/{pid}/stat") as f:
			state = f.read().rsplit(")", 1)[1].split()[0]
		return state not in ("Z", "X")
	except (OSError, IndexError):
		return True  # no /proc (not Linux): trust kill(0)


def watched_gui_pid() -> int | None:
	"""PID of the GUI that started this daemon, or None when it was started some other way (command line, service)."""
	raw = os.environ.get(GUI_PID_ENV, "")
	return int(raw) if raw.isdigit() else None
