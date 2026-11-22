# SC Controller (updated)

A fork of [C0rn3j/sc-controller](https://github.com/C0rn3j/sc-controller) (v1.0.3), the GTK 4 user-mode driver and mapper for Steam Controller, Steam Deck and other game controllers. This fork focuses on making the app easier and more predictable to use with Steam-type controllers. The driver and mapping engine are unchanged.

The original README is kept as [README.upstream.md](README.upstream.md). All credit for the app itself goes to the upstream authors.

## What is different

- **Closing the window quits everything.** The background daemon stops too, so the controller returns to normal desktop behaviour instead of staying mapped. (`autokill_daemon` now defaults to on; it is still a setting.)
- **One Controller dropdown.** With a Steam Deck and a Steam Controller connected, a single "Controller:" dropdown above the "Profile:" dropdown picks which one you are editing, instead of two stacked profile rows. Both controllers keep running with their own profiles. The dropdown is always shown (greyed out when there is nothing to choose), remembers your choice, and prefers an external controller over the Deck's built-in one.
- **Unplugging is handled.** If the controller you are editing disappears, the window switches to the remaining one and redraws its diagram.
- **Save always asks where.** Changes apply live to the running controller, even if you never save them. The Save button always opens a "Save profile as..." file dialog, so nothing is written to a profile file by accident.
- **Cleaner startup.** The window opens at its normal size showing "Loading..." and reveals the controls once the controller layout is ready, instead of opening huge and then shrinking.
- **Dark theme by default** and software rendering by default, which removes the EGL/Vulkan renderer warnings printed inside AppImages.
- **Missing icons fixed** in the AppImage (for example the OK button in the action editor): the standard Adwaita symbolic icons are bundled.

## Planned

- Simpler Import / Export of profiles (one-click export, preview before import, no silent overwrites).
- A portable AppImage that keeps its configuration next to the AppImage instead of in `~/.config`.

## Building and running

Build and packaging instructions are the same as upstream; see [README.upstream.md](README.upstream.md) and the `AppImageBuilder*.yml` files. To run from a source checkout, install the dependencies listed upstream and use `./run.sh`.

## Status

Work in progress, tested mainly on a Steam Deck with a Steam Controller (2015). Bug reports are welcome.

## License

GPL v2, the same as upstream. See [LICENSE](LICENSE) and [ADDITIONAL-LICENSES](ADDITIONAL-LICENSES). Any distributed build must stay GPL v2 and provide its source.
