"""KiCad action plugins: teardrops at T junctions (core: ../teardrop_t.py). Installed from the zip that ../package.py builds
(KiCad: Plugin and Content Manager, "Install from File"), which carries a copy of the core as teardrop_core.py; without that copy (a
symlink to this folder) the core is found through the real path of this file.
The folder is not called teardrop_t: KiCad imports it under its folder name, and `import teardrop_t` would then return this plugin
instead of the core (the core is loaded from its file path for the same reason). Registered unconditionally, like every KiCad plugin:
importing this outside KiCad aborts the interpreter (register() needs KiCad's Pgm); the core has its own --selftest."""
import importlib.util
import os

import pcbnew

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(HERE)
ICON = os.path.join(HERE, "icon.png")
DARK_ICON = os.path.join(HERE, "icon-dark.png")  # KiCad picks it on the dark theme


def core():
    bundled = os.path.join(HERE, "teardrop_core.py")  # the copy inside the package (package.py, installed from file by KiCad's PCM)
    path = bundled if os.path.exists(bundled) else os.path.join(REPO, "teardrop_t.py")
    spec = importlib.util.spec_from_file_location("mt_teardrop_t_core", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TeardropT(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "T-Junction Teardrops"
        self.category = "Marine Telematics"
        self.description = "Copper fillets at the corners of T-junctions, on the selected tracks or the whole board"
        self.show_toolbar_button = True
        self.icon_file_name = ICON
        self.dark_icon_file_name = DARK_ICON

    def Run(self):
        import wx
        from . import dialog
        board = pcbnew.GetBoard()
        with dialog.TeardropDialog(None, board, core()) as box:
            box.ShowModal()


TeardropT().register()
