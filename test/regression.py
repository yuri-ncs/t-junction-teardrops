"""Regression of teardrop_t on the synthetic board (make_board.py): builds the board, adds the wedges with the DEFAULTS, fills the zones with
the kicad-cli DRC, and requires a DRC with no violation and no unconnected item, no wedge empty or cut (the fill covers the whole outline:
no clearance horn) and the expected wedge count of each case (make_board.WEDGES). Writes out/wedges.kicad_pcb and out/sheet.png (each case
enlarged, with the real fill in orange and the zone outline dashed). Run with KiCad's python:  $PY test/regression.py"""
import collections
import json
import math
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
sys.path.insert(0, os.path.dirname(HERE))
import pcbnew  # noqa: E402
import teardrop_t as t  # noqa: E402

K = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
RSVG = "/opt/homebrew/bin/rsvg-convert"
R, PX, COLS = 2.5, 200, 6  # half window (mm), panel side (px), columns
FILL_MIN = 0.95  # filled / outline: below this another net's clearance cut the wedge


def sheet(board, cases, png, r=R, px=PX, cols=COLS):
    """Contact sheet of the cases: tracks, pads and vias near each node, the wedge fill in orange and the zone outline dashed. The SVG
    goes to out/, the PNG to `png`."""
    tracks = [x for x in board.GetTracks() if x.Type() == pcbnew.PCB_TRACE_T]
    vias = [x for x in board.GetTracks() if x.Type() == pcbnew.PCB_VIA_T]
    pads = list(board.GetPads())
    zones = [z for z in board.Zones() if z.GetZoneName() == t.NAME]
    k = px / (2 * r)
    panels = []
    for i, c in enumerate(cases):
        n = c["node"]
        lay = board.GetLayerID(c["layer"])
        ox, oy = (i % cols) * (px + 8), (i // cols) * (px + 24)
        f = lambda x, y: (ox + (x - n[0] + r) * k, oy + 18 + (y - n[1] + r) * k)  # noqa: E731
        g = ['<clipPath id="c%d"><rect x="%.1f" y="%.1f" width="%d" height="%d"/></clipPath>' % (i, ox, oy + 18, px, px),
             '<rect x="%.1f" y="%.1f" width="%d" height="%d" fill="#101418"/><g clip-path="url(#c%d)">' % (ox, oy + 18, px, px, i)]

        def poly(sh, fill, extra=""):
            for o in range(sh.OutlineCount()):
                ln = sh.Outline(o)
                pts = " ".join("%.1f,%.1f" % f(pcbnew.ToMM(ln.CPoint(q).x), pcbnew.ToMM(ln.CPoint(q).y)) for q in range(ln.PointCount()))
                g.append('<polygon points="%s" fill="%s" %s/>' % (pts, fill, extra))
        for pad in pads:
            if pad.IsOnLayer(lay) and math.dist(n, pcbnew.ToMM(pad.GetPosition())) < 2 * r:
                poly(pad.GetEffectivePolygon(lay), "#B8860B" if pad.GetNetname() == c["net"] else "#5a5a5a")
        for tr in tracks:
            a, b = pcbnew.ToMM(tr.GetStart()), pcbnew.ToMM(tr.GetEnd())
            if tr.GetLayer() == lay and min(math.dist(n, a), math.dist(n, b)) < 8:
                (x1, y1), (x2, y2) = f(*a), f(*b)
                g.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%.1f" stroke-linecap="round"/>'
                         % (x1, y1, x2, y2, "#C83434" if tr.GetNetname() == c["net"] else "#7a3a3a", pcbnew.ToMM(tr.GetWidth()) * k))
        for v in vias:
            p = pcbnew.ToMM(v.GetPosition())
            if math.dist(n, p) < 2 * r:
                x, y = f(*p)
                g.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#C8A040"/><circle cx="%.1f" cy="%.1f" r="%.1f" fill="#101418"/>'
                         % (x, y, pcbnew.ToMM(v.GetWidth(lay)) / 2 * k, x, y, pcbnew.ToMM(v.GetDrillValue()) / 2 * k))
        for z in zones:
            if z.GetLayer() == lay and math.dist(n, pcbnew.ToMM(z.Outline().COutline(0).CPoint(0))) < 0.01:
                if z.HasFilledPolysForLayer(lay):
                    poly(z.GetFilledPolysList(lay), "#F2A93B", 'opacity="0.95"')
                poly(z.Outline(), "none", 'stroke="#fff" stroke-width="0.7" stroke-dasharray="2,2"')
        g.append('</g><text x="%.1f" y="%.1f" fill="#ddd" font-size="11" font-family="Helvetica">%s. %s</text>' % (ox + 2, oy + 13, c["id"], c["name"]))
        panels.append("".join(g))
    rows = (len(panels) + cols - 1) // cols
    svg = os.path.join(OUT, os.path.basename(png)[:-4] + ".svg")
    open(svg, "w").write('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d"><rect width="100%%" height="100%%" fill="#1b1f24"/>%s</svg>'
                          % (cols * (px + 8), rows * (px + 24), "".join(panels)))
    subprocess.run([RSVG, svg, "-o", png], check=True)


def build(p=None, name="wedges"):
    """The test board (make_board.py) with the wedges of p (None: DEFAULTS), filled by the kicad-cli DRC. -> (board, DRC report, cases)"""
    subprocess.run([sys.executable, os.path.join(HERE, "make_board.py")], check=True, capture_output=True)
    cases = json.load(open(os.path.join(OUT, "cases.json")))
    board = pcbnew.LoadBoard(os.path.join(OUT, "test_board.kicad_pcb"))
    t.add(board, p=p)
    pcbnew.SaveBoard(os.path.join(OUT, name + ".kicad_pcb"), board)
    shutil.copy(os.path.join(OUT, "test_board.kicad_pro"), os.path.join(OUT, name + ".kicad_pro"))  # SaveBoard writes a default project
    subprocess.run([K, "pcb", "drc", "--refill-zones", "--save-board", "--format", "json", "--severity-all", "-o", name + "-drc.json",
                    name + ".kicad_pcb"], cwd=OUT, capture_output=True, check=True)
    return pcbnew.LoadBoard(os.path.join(OUT, name + ".kicad_pcb")), json.load(open(os.path.join(OUT, name + "-drc.json"))), cases


def main():
    board, drc, cases = build()
    zones = [z for z in board.Zones() if z.GetZoneName() == t.NAME]
    got, fill = collections.Counter(), {}
    for z in zones:
        node = pcbnew.ToMM(z.Outline().COutline(0).CPoint(0))
        case = next(c for c in cases if c["net"] == z.GetNetname() and math.dist(node, c["node"]) < 0.01)
        got[case["id"]] += 1
        filled = z.GetFilledPolysList(z.GetLayer()).Area() if z.HasFilledPolysForLayer(z.GetLayer()) else 0
        fill.setdefault(case["id"], []).append(filled / z.Outline().Area())
    sheet(board, cases, os.path.join(OUT, "sheet.png"))
    bad = []
    for c in cases:
        ok = got[c["id"]] == c["wedges"] and all(r >= FILL_MIN for r in fill.get(c["id"], []))
        print("%-4s %-4s %-28s wedges %d (expected %d)  filled %s" % ("ok" if ok else "FAIL", c["id"], c["name"], got[c["id"]], c["wedges"],
              " ".join("%.0f%%" % (100 * r) for r in fill.get(c["id"], []))))
        if not ok:
            bad.append(c["id"])
    violations = collections.Counter(v["type"] for v in drc["violations"])
    print("DRC:", dict(violations) or "clean", "| unconnected:", len(drc["unconnected_items"]), "| sheet:", os.path.join(OUT, "sheet.png"))
    assert not bad and not violations and not drc["unconnected_items"], (bad, dict(violations))
    print("regression ok")


if __name__ == "__main__":
    main()
