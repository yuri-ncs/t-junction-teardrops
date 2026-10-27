"""Builds the KiCad package of the T-junction teardrop plugin: dist/mt_teardrop_t-<VERSION>.zip, to install in KiCad with
Plugin and Content Manager -> "Install from File". Layout of a PCM package (schema go.kicad.org/pcm/schemas/v2):
  metadata.json, plugins/ (the action plugin: __init__.py, dialog.py, icon.png, icon-dark.png and teardrop_core.py, a copy of teardrop_t.py), resources/icon.png.
With --submission it also writes dist/submission/<identifier>/ (metadata.json with the download_* fields of the GitHub release asset,
and icon.png): the folder that goes to packages/ in a merge request to gitlab.com/kicad/addons/metadata. Upload that same zip to the
release: rebuilding it changes the sha256.
Run with any python3:  python3 package.py [--submission]
"""
import hashlib
import json
import os
import shutil
import sys
import zipfile

VERSION = "0.4.4"  # see CHANGELOG.md
REPO = "https://github.com/yuri-ncs/t-junction-teardrops"
HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(HERE, "mt_teardrop_t")
METADATA = {
    "$schema": "https://go.kicad.org/pcm/schemas/v2",
    "name": "T-Junction Teardrops",
    "description": "Fillets at the corners of T-junctions between tracks",
    "description_full": "KiCad only adds a track-to-track teardrop where the width changes. This plugin fills the corners of every "
                        "T-junction (same net and layer, away from pads and vias) with copper, one T-td zone per corner.",
    "identifier": "com.github.yuri-ncs.t-junction-teardrops",  # the store's rule for GitHub-hosted packages: com.github.<user>.<repo>
    "type": "plugin",
    "author": {"name": "Yuri Neves", "contact": {"email": "yurineves2204@gmail.com"}},
    "license": "MIT",
    "resources": {"homepage": REPO},
    "tags": ["pcb", "routing", "teardrops"],
    "versions": [{"version": VERSION, "status": "stable", "kicad_version": "10.0", "runtime": "swig"}],  # tested on KiCad 10 only
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


def submission(path):
    """dist/submission/<identifier>/: metadata.json with the download fields of `path` as a release asset, and icon.png. -> the folder"""
    folder = os.path.join(HERE, "dist", "submission", METADATA["identifier"])
    os.makedirs(folder, exist_ok=True)
    data = open(path, "rb").read()
    with zipfile.ZipFile(path) as z:
        install = sum(i.file_size for i in z.infolist())
    version = {**METADATA["versions"][0], "download_url": "%s/releases/download/v%s/%s" % (REPO, VERSION, os.path.basename(path)),
               "download_sha256": hashlib.sha256(data).hexdigest(), "download_size": len(data), "install_size": install}
    with open(os.path.join(folder, "metadata.json"), "w") as f:
        json.dump({**METADATA, "versions": [version]}, f, indent=2, ensure_ascii=False)
    shutil.copy(os.path.join(PLUGIN, "icon-64.png"), os.path.join(folder, "icon.png"))
    return folder


if __name__ == "__main__":
    path = build()
    with zipfile.ZipFile(path) as z:
        assert sorted(z.namelist()) == ["metadata.json", "plugins/__init__.py", "plugins/dialog.py", "plugins/icon-dark.png", "plugins/icon.png", "plugins/teardrop_core.py", "resources/icon.png"]
        meta = json.loads(z.read("metadata.json"))
        assert meta["identifier"] == METADATA["identifier"] and not any(k.startswith("download") for k in meta["versions"][0])
    print(path)
    if "--submission" in sys.argv:
        print(submission(path))
