"""Renders the plugin icons from their SVG sources (needs rsvg-convert, Homebrew librsvg):
icon.png (24 px, light toolbar), icon-dark.png (24 px, dark theme) and icon-64.png (Plugin and Content Manager).
Colours from KiCad itself: the F.Cu red for the track, amber for the fillets the tool adds; green solder mask behind the 64 px tile."""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
for name, size in (("icon", 24), ("icon-dark", 24), ("icon-64", 64)):
    subprocess.run(["/opt/homebrew/bin/rsvg-convert", "-w", str(size), "-h", str(size), "-o", os.path.join(HERE, name + ".png"),
                    os.path.join(HERE, name + ".svg")], check=True)
