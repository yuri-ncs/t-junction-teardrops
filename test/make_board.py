"""Synthetic board with 22 kinds of junction to test teardrop_t: T junctions of several widths, branches at 45/30/15 degrees, Y splits,
crosses, a pad or via next to the node, another net nearby, very short arms, F/B/In2, and three junctions copied from a real board.
Every loose track end gets a pad of its net (round, as wide as the track; PTH on In2), so the board's DRC is clean: no dangling track
and no isolated copper, which KiCad reports for a net without pads. Writes out/test_board.kicad_pcb and out/cases.json. Run with
KiCad's python (regression.py runs it)."""
import json
import os
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
# wedges expected per case with the DEFAULTS of teardrop_t (120 degree limit, 25 % minimum length, other nets' clearance)
WEDGES = {1: 2, 2: 2, 3: 2, 4: 2, 5: 1, 6: 1, 7: 3, 8: 1, 9: 4, 10: 3, 11: 2, 12: 1, 13: 1, 14: 0, 15: 1, 16: 2, 17: 0, 18: 0, 19: 1,
          20: 2, 21: 2, 22: 1}
S, P = 0.25, 0.8
mm = pcbnew.FromMM
board = pcbnew.BOARD()
board.SetCopperLayerCount(4)
nets = {}
LAYER = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu, "In2": pcbnew.In2_Cu}


def net(name):
    if name not in nets:
        nets[name] = pcbnew.NETINFO_ITEM(board, name, len(nets) + 1)
        board.Add(nets[name])
    return nets[name]


def vec(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def poly(o, name, pts, w, layer="F"):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(vec(o[0] + x0, o[1] + y0))
        t.SetEnd(vec(o[0] + x1, o[1] + y1))
        t.SetWidth(mm(w))
        t.SetLayer(LAYER[layer])
        t.SetNet(net(name))
        board.Add(t)


def pad(o, name, ref, x, y, w, h):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    fp.Reference().SetVisible(False)
    fp.SetPosition(vec(o[0] + x, o[1] + y))
    p = pcbnew.PAD(fp)
    p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetLayerSet(p.SMDMask())
    p.SetSize(pcbnew.VECTOR2I(mm(w), mm(h)))
    p.SetPosition(vec(o[0] + x, o[1] + y))
    p.SetNet(net(name))
    fp.Add(p)
    board.Add(fp)


def via(o, name, x, y):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(vec(o[0] + x, o[1] + y))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetWidth(mm(0.6))
    v.SetDrill(mm(0.3))
    v.SetNet(net(name))
    board.Add(v)


T = [(-4, 0), (4, 0)]
B = [(0, 0), (0, 4)]
cases = []  # (id, name, layer, expected, builder(o, n))


def add(i, name, expected, fn, layer="F"):
    cases.append((i, name, layer, expected, fn))


add(1, "T, signal", "2 wedges, in the 90° corners", lambda o, n: (poly(o, n, T, S), poly(o, n, B, S)))
add(2, "T, power", "2 wedges", lambda o, n: (poly(o, n, T, P), poly(o, n, B, P)))
add(3, "Wide trunk, narrow branch", "2 wedges", lambda o, n: (poly(o, n, T, P), poly(o, n, B, S)))
add(4, "Narrow trunk, wide branch", "2 wedges", lambda o, n: (poly(o, n, T, S), poly(o, n, B, P)))
add(5, "45° branch", "only the 45° corner (135° is over the limit)",
    lambda o, n: (poly(o, n, T, S), poly(o, n, [(0, 0), (3, 3)], S)))
add(6, "30° branch", "a wedge in the 30° corner",
    lambda o, n: (poly(o, n, T, S), poly(o, n, [(0, 0), (3.464, 2)], S)))
add(7, "Y, 120°", "all three 120° corners",
    lambda o, n: [poly(o, n, [(0, 0), a], S) for a in [(0, -4), (3.464, 2), (-3.464, 2)]])
add(8, "Y with short legs", "only the 90° corner (copied from a real board)", lambda o, n: [poly(o, n, p, 0.2) for p in [
    [(0, 0), (-0.46, -0.46), (-0.46, -4)], [(0, 0), (0.63, 0), (3, 2.37)], [(0, 0), (-1.25, 1.25), (-1.25, 4)]]])
add(9, "Cross", "4 wedges",
    lambda o, n: [poly(o, n, p, S) for p in [T, [(0, -4), (0, 0)], [(0, 0), (0, 4)]]])
add(10, "Four-way star", "the 45° and 90° corners; 135° is over the limit",
    lambda o, n: [poly(o, n, [(0, 0), a], S) for a in [(4, 0), (3, 3), (-4, 0), (0, -4)]])


def c11(o, n):
    poly(o, n, [(-3, 0), (3, 0)], P)
    poly(o, n, [(0, 0), (0, -3)], P)
    pad(o, n, "P11a", -1.25, 0, 0.9, 0.95)
    pad(o, n, "P11b", 1.6, 0, 0.9, 0.95)


add(11, "Pads close to the T", "a wedge only where there is room up to the pad, never over it", c11)


def c12(o, n):
    poly(o, n, [(0, 0), (0, -1.1), (-2, -3.1)], 0.65, "B")
    poly(o, n, [(0, 0), (5, 0)], 0.65, "B")
    poly(o, n, [(0, 0), (0, 0.7)], 0.65, "B")
    via(o, n, 0, 0.7)
    poly(o, n, [(0, 0.7), (0, 2.5)], 0.65)  # the via ties the B.Cu track to an F.Cu one, or the DRC flags it dangling


add(12, "Via next to the T (B.Cu)", "only the corner away from the via (copied from a real board)", c12, "B")


def c13(o, n):
    poly(o, n, [(-1.402, -1.947), (0, -0.545), (0, 0), (0, 0.676), (-0.627, 1.303), (-1.402, 1.303)], 0.2)
    poly(o, n, [(0, 0), (2.418, 2.418)], 0.2)


add(13, "Branch off a zig-zag", "only the 45° corner (copied from a real board)", c13)


def c14(o, n):
    poly(o, n, T if False else [(-3, 0), (3, 0)], P)
    poly(o, n, [(0, 0), (0, 0.6)], P)
    pad(o, n, "P14a", 0, 0.9, 0.9, 0.9)


add(14, "Short branch into a pad", "none: it is a pad entry", c14)


def c15(o, n):
    poly(o, n, [(-4, 0), (0, 0), (0.6, 0)], P)
    pad(o, n, "P15a", 1.4, 0, 1.6, 1.6)
    poly(o, n, [(0, 0), (0, -4)], P)


add(15, "Trunk into a pad", "only the left corner", c15)


def c16(o, n):
    poly(o, n, T, S)
    poly(o, n, B, S)
    poly(o, n + "_OUT", [(0.55, 0.5), (0.55, 4)], S)


add(16, "Other net nearby", "the right wedge shrinks to the clearance, with no copper horn", c16)
add(17, "L corner", "none", lambda o, n: poly(o, n, [(-4, 0), (0, 0), (0, 4)], S))
add(18, "Width change", "none",
    lambda o, n: (poly(o, n, [(-4, 0), (0, 0)], P), poly(o, n, [(0, 0), (4, 0)], S)))
add(19, "Branch at a bend", "only the 90° corner",
    lambda o, n: (poly(o, n, [(-4, 0), (0, 0), (2.83, -2.83)], S), poly(o, n, B, S)))
add(20, "T on In2.Cu", "2 wedges", lambda o, n: (poly(o, n, T, S, "In2"), poly(o, n, B, S, "In2")), "In2")


def c21(o, n):
    poly(o, n, [(-0.35, 0), (0.35, 0)], S)
    pad(o, n, "P21a", -0.65, 0, 0.6, 0.6)
    pad(o, n, "P21b", 0.65, 0, 0.6, 0.6)
    poly(o, n, B, S)


add(21, "Very short arms", "2 small wedges", c21)
add(22, "15° branch", "a thin wedge in the 15° corner",
    lambda o, n: (poly(o, n, T, S), poly(o, n, [(0, 0), (4, 1.072)], S)))



def close_ends():
    """A pad of the net on every track end used by one track only, outside pads and vias and off other tracks of the same net."""
    tracks = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    ends = {}
    for t in tracks:
        for e in (t.GetStart(), t.GetEnd()):
            k = (t.GetNetCode(), t.GetLayer(), e.x, e.y)
            ends[k] = (ends[k][0] + 1, t) if k in ends else (1, t)
    holes = [(p.GetNetCode(), p) for p in board.GetPads()] + [(v.GetNetCode(), v) for v in board.GetTracks() if v.Type() == pcbnew.PCB_VIA_T]
    for (code, layer, x, y), (count, t) in ends.items():
        q = pcbnew.VECTOR2I(x, y)
        if count > 1 or any(c == code and h.HitTest(q) for c, h in holes):
            continue
        if any(o.GetNetCode() == code and o.GetLayer() == layer and o is not t and o.HitTest(q, 0) for o in tracks):
            continue  # an end on another track of the net: a junction
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference("E%d" % len(board.GetFootprints()))
        fp.Reference().SetVisible(False)
        fp.SetPosition(q)
        p = pcbnew.PAD(fp)
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        if layer == pcbnew.In2_Cu:
            p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            p.SetLayerSet(p.PTHMask())
            p.SetSize(pcbnew.VECTOR2I(mm(0.6), mm(0.6)))
            p.SetDrillSize(pcbnew.VECTOR2I(mm(0.3), mm(0.3)))
        else:
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            ls = pcbnew.LSET()
            ls.AddLayer(layer)
            ls.AddLayer(pcbnew.F_Mask if layer == pcbnew.F_Cu else pcbnew.B_Mask)
            p.SetLayerSet(ls)
            p.SetSize(pcbnew.VECTOR2I(t.GetWidth(), t.GetWidth()))
        p.SetPosition(q)
        p.SetNet(t.GetNet())
        fp.Add(p)
        board.Add(fp)


out = []
for i, name, layer, expected, fn in cases:
    o = (20 + 12 * ((i - 1) % 5), 20 + 12 * ((i - 1) // 5))
    n = f"C{i}"
    fn(o, n)
    t = pcbnew.PCB_TEXT(board)
    t.SetText(str(i))
    t.SetLayer(pcbnew.Cmts_User)
    t.SetPosition(vec(o[0] - 5, o[1] - 5))
    t.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
    board.Add(t)
    out.append({"id": i, "name": name, "net": n, "layer": {"F": "F.Cu", "B": "B.Cu", "In2": "In2.Cu"}[layer],
                "node": list(o), "wedges": WEDGES[i], "expected": expected})
close_ends()

x0, y0, x1, y1 = 20 - 5 - 3, 20 - 5 - 3, 20 + 48 + 5 + 3, 20 + 48 + 5 + 3
pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
for (a, b), (c, d) in zip(pts, pts[1:]):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetStart(vec(a, b))
    s.SetEnd(vec(c, d))
    s.SetWidth(mm(0.1))
    board.Add(s)

os.makedirs(OUT, exist_ok=True)
pcbnew.SaveBoard(os.path.join(OUT, "test_board.kicad_pcb"), board)
json.dump(out, open(os.path.join(OUT, "cases.json"), "w"), ensure_ascii=False, indent=1)
