# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What it is
"T-Junction Teardrops", a KiCad action plugin. It fills the corners of every track T-junction with copper, one `T-td` zone per corner. `README.md` describes the usage, the rules and the reason behind each default.

- `teardrop_t.py`: the core. It finds the junctions, draws the wedges, and has `add`/`remove`/`plan`/`outdated` and the self-test. It does not use wx, so it also runs outside KiCad.
- `mt_teardrop_t/`: the plugin. `__init__.py` registers the action and loads the core by file path. `dialog.py` is the wx dialog with the preview.
- `package.py`: builds `dist/mt_teardrop_t-<VERSION>.zip` (PCM, schema v1), with a copy of the core as `plugins/teardrop_core.py`. `VERSION` carries the changelog.
- `test/`: the synthetic board of 22 cases (`make_board.py`, with the expected wedge counts in `WEDGES`) and the regression (`regression.py`).
- `docs/`: the README images and `make_images.py`, which renders them again.
- Other scripts may import the core: keep `add`, `load`, `params_path` and `NAME` stable.

## Run
```
PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
```
- `$PY teardrop_t.py --selftest`
- `$PY test/regression.py`: needs `kicad-cli` and writes to `test/out/`, which is not in git.
- `$PY docs/make_images.py`: opens the dialog for a moment.
- `python3 package.py` (any python3). Install the zip in KiCad with Plugin and Content Manager → Install from File. After changing the core or the dialog, bump `VERSION`, build the zip again and reinstall.

## Rules
- Documents, comments and commit messages are in English.
- **A new geometry rule goes in three places at once:**
  - the self-test in `teardrop_t.py`;
  - a case in `test/make_board.py`, with its count in `WEDGES`;
  - a row of the README table, with the reason.
- What `plan()` decides holds for `add()`, `outdated()` and the dialog count. Put a new rule in `plan()` or `corner()`, never in the dialog.
- The plugin edits the board only inside `Run()`. KiCad records the plugin's changes (undo entry, unsaved mark) only between the start and the end of `Run()`, so the dialog stays modal.
- **Metadata:** name and description in English, identifier `com.teardropt`. The author's e-mail appears only in the metadata.

## Pitfalls (KiCad 10 SWIG)
- `Clone()` of a zone, and adding back a removed zone, crash or leave dead wrappers. The dialog keeps the zones as plain data instead (`snapshot`/`rebuild`).
- `GetOwnClearance` returns 0 on a new `pcbnew.BOARD()` with no rules. Only a board loaded from disk has the net class clearances, so the self-test checks clearance by geometry only and the regression checks it with the DRC.
- `pad.HitTest` answers for an area larger than the copper. For the pad edge, use `GetEffectivePolygon(layer).Contains`.
- **Importing the plugin outside KiCad:**
  - importing `mt_teardrop_t/__init__.py` outside KiCad aborts the interpreter, because `register()` needs KiCad's Pgm;
  - to test the dialog, import `dialog.py` directly with a `wx.App()`, as `docs/make_images.py` does;
  - the plugin folder must not be called `teardrop_t`: KiCad imports it by its folder name, and `import teardrop_t` would then get the plugin.

## Open items
- **KiCad store (PCM):** public repository URL in the metadata, schema v2, category (now `Marine Telematics`), and the zip's sha256 and size in the submission.
- A version for the IPC API: KiCad 11 drops SWIG. It would also leave KiCad usable while the dialog is open.
