"""Builds the KiCad package of the T-junction teardrop plugin: dist/mt_teardrop_t-<VERSION>.zip, to install in KiCad with
Plugin and Content Manager -> "Install from File". Layout of a PCM package (schema go.kicad.org/pcm/schemas/v1):
  metadata.json, plugins/ (the action plugin: __init__.py, dialog.py, icon.png, icon-dark.png and teardrop_core.py, a copy of teardrop_t.py), resources/icon.png.
Run with any python3:  python3 package.py
"""
import json
import os
import zipfile

VERSION = "0.4.3"  # 0.4.3: the clearance check looks as far as the board's biggest clearance (was a fixed 1 mm); 0.4.2: max corner angle 120 (was 179, inclusive and rounded to 0.1 degree), min length 25 % of the width, a wedge stops short of other nets' copper by its clearance (no copper horn from the fill), "Min length (% of width)" in the dialog; 0.4.1: a wedge stops at the first pad/via of its net, and a branch from the middle of a segment measures each side apart; 0.4.0: exclusions (nets by pattern, net classes) and the out-of-date wedge line with an "Update out-of-date" button; 0.3.0: parameter dialog with live preview (plugins/dialog.py), Remove mode instead of a separate remove action; 0.2.2: identifier com.teardropt, author e-mail; 0.2.1: new icon (light/dark toolbar, 64 px tile); 0.2.0: one zone per corner holding the half track (tips filled to the tangent); 0.1.1: fill down to 0.0254 mm
HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(HERE, "mt_teardrop_t")
METADATA = {
    "$schema": "https://go.kicad.org/pcm/schemas/v1",
    "name": "T-Junction Teardrops",
    "description": "Fillets at the corners of T-junctions between tracks",
    "description_full": "KiCad only adds a track-to-track teardrop where the width changes. This plugin fills the corners of every "
                        "T-junction (same net and layer, away from pads and vias) with copper, one T-td zone per corner.",
    "identifier": "com.teardropt",
    "type": "plugin",
    "author": {"name": "Yuri Neves", "contact": {"email": "yurineves2204@gmail.com"}},
    "license": "MIT",  # the schema has no proprietary option
    "resources": {},
    "versions": [{"version": VERSION, "status": "stable", "kicad_version": "9.0", "runtime": "swig"}],
}


def build():
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    out = os.path.join(HERE, "dist", "mt_teardrop_t-%s.zip" % VERSION)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("metadata.json", json.dumps(METADATA, indent=2, ensure_ascii=False))
        z.write(os.path.join(PLUGIN, "__init__.py"), "plugins/__init__.py")
        z.write(os.path.join(PLUGIN, "dialog.py"), "plugins/dialog.py")
        z.write(os.path.join(PLUGIN, "icon.png"), "plugins/icon.png")
        z.write(os.path.join(PLUGIN, "icon-dark.png"), "plugins/icon-dark.png")
        z.write(os.path.join(HERE, "teardrop_t.py"), "plugins/teardrop_core.py")
        z.write(os.path.join(PLUGIN, "icon-64.png"), "resources/icon.png")
    return out


if __name__ == "__main__":
    path = build()
    with zipfile.ZipFile(path) as z:
        assert sorted(z.namelist()) == ["metadata.json", "plugins/__init__.py", "plugins/dialog.py", "plugins/icon-dark.png", "plugins/icon.png", "plugins/teardrop_core.py", "resources/icon.png"]
        assert json.loads(z.read("metadata.json"))["identifier"] == METADATA["identifier"]
    print(path)
