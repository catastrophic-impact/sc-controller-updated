# SC Controller (updated)

A fork of [C0rn3j/sc-controller](https://github.com/C0rn3j/sc-controller) (v1.0.3), the GTK 4 user-mode driver and mapper for Steam Controller, Steam Deck and other game controllers. This fork focuses on making the app easier and more predictable to use with Steam-type controllers. The driver and mapping engine are unchanged.

The original README is kept as [README.upstream.md](README.upstream.md). All credit for the app itself goes to the upstream authors.

## What is different

- **Closing the window quits everything.** The background daemon stops too, so the controller returns to normal desktop behaviour instead of staying mapped. (`autokill_daemon` now defaults to on; it is still a setting.)
- **Crash-safe.** If the window crashes or is force-killed, the background program notices within a few seconds and stops too, so the controller is not left remapped. (Only when "stop daemon on close" is on, which is the default.)
- **One Controller dropdown.** With a Steam Deck and a Steam Controller connected, a single "Controller:" dropdown above the "Profile:" dropdown picks which one you are editing, instead of two stacked profile rows. Both controllers keep running with their own profiles. The dropdown is always shown (greyed out when there is nothing to choose), remembers your choice, and prefers an external controller over the Deck's built-in one.
- **Unplugging is handled.** If the controller you are editing disappears, the window switches to the remaining one and redraws its diagram.
- **Save always asks where.** Changes apply live to the running controller, even if you never save them. The Save button always opens a "Save profile as..." file dialog, so nothing is written to a profile file by accident.
- **Cleaner startup.** The window opens at its normal size showing "Loading..." and reveals the controls once the controller layout is ready, instead of opening huge and then shrinking.
- **Dark theme by default** and software rendering by default, which removes the EGL/Vulkan renderer warnings printed inside AppImages.
- **Missing icons fixed** in the AppImage (for example the OK button in the action editor): the standard Adwaita symbolic icons are bundled.

## Import / Export

- **Export profile...** saves the profile you are editing (including changes you have not saved) with one file dialog. If it uses other profiles or menus they are bundled automatically.
- **Import profile...** opens a preview first: you see the name, anything else that comes with it, and a warning if it runs shell commands. If the name is taken you choose between a new copy (the default) or replacing; nothing is overwritten silently, and built-in profiles are never replaced. A note appears if the profile was made for a different controller.
- Importing Steam profiles and the original wizard are still available under **Import Steam profile (advanced)...**.

The logic is in `scc/profile_package.py` and is covered by `tests/test_profile_package.py` (round trips, name clashes, reference rewriting, unsafe archives).

## Portable

When run as an AppImage, all settings, data and cache are stored in a `config` folder next to the `.AppImage` file, never in `~/.config`. Set `SCC_CONFIG_DIR` to choose another location.

## Building and running

Build and packaging instructions are the same as upstream; see [README.upstream.md](README.upstream.md) and the `AppImageBuilder*.yml` files. To run from a source checkout, install the dependencies listed upstream and use `./run.sh`.

## Status

Work in progress, tested mainly on a Steam Deck with a Steam Controller (2015). Bug reports are welcome.

## License

GPL v2, the same as upstream. See [LICENSE](LICENSE) and [ADDITIONAL-LICENSES](ADDITIONAL-LICENSES). Any distributed build must stay GPL v2 and provide its source.
