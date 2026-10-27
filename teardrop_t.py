"""T-junction teardrops: extra copper in the corners of every T (and cross) between tracks of the same net and layer.
Run with KiCad's python:  teardrop_t.py in.kicad_pcb out.kicad_pcb      (self-check: teardrop_t.py --selftest)
KiCad only makes a track-to-track teardrop when the width changes; a same-width T gets nothing. Here every T is reinforced like a pad:
each corner between two neighbouring branches gets a wedge:
the two track edges facing the corner meet at C; the wedge runs from C along each edge for L and is closed by a concave fillet arc
tangent to both edges (radius L*tan(theta/2)), or by a straight line (`straight`, a triangle) where the arc breaks the DRC.
L = min(3 x the narrower width, 1.0 mm), cut to the free length of the shorter branch (with 1.5 x the fillet on a 0.2 mm track was
barely visible: a 90 degree fillet is at most 0.41 L thick, on the bisector). The fill keeps copper down to MIN_FILL_MM, so the fillet
tapers to the track edge like KiCad's own teardrops.
Each corner is its own ZONE named "T-td" (one object per side): node, along A's axis to level with PA, out to PA, the arc,
PB, back along B's axis. Holding the half track (axis to edge) makes the fillet tip a concave corner of solid copper, so the fill
reaches the tangent points (a fillet alone tapers below MIN_FILL_MM and its last ~0.17 mm stayed empty, as KiCad's teardrops avoid by
holding the track); and the node, where the track ends meet, lies in the fill, so KiCad sees the zone connected (a wedge that started at
C was emptied by island removal). Corners of one junction meet on the axes and never overlap; full connection, no own clearance, NOT a
KiCad teardrop area (KiCad deletes those when it rebuilds). Priority above every pour so a GND plane yields, distinct from each other
(zones of nodes closer than a track width overlap). add() does not refill zones: the caller does.
A junction key is "NET@x,y" (node in mm, 3 decimals); a wedge zone's first outline vertex is its node,
so zone_key() finds the junction of an existing zone and add()/remove() can work on a filtered scope without touching the rest.
Parameters (DEFAULTS; the plugin dialog edits them, saved next to the board as <board>.teardrop_t.json):
length_pct and max_length_mm (L = min(length_pct % of the narrower width, max_length_mm)), min_length_mm and min_length_pct (a wedge
shorter than either, the second as a % of the narrower width, is not made), max_angle_deg (corners up to it, inclusive), min_fill_mm,
curved, t_junctions (3 branches) / crossings (4+), the filters net, netclass, layer (names; None = all), and the exclusions exclude_nets
(comma-separated fnmatch patterns, e.g. "USB_D*, RF_*": the extra copper changes a controlled impedance) and exclude_netclasses (names).
Defaults (from the test board of 22 junction kinds in test/): max_angle_deg 120, since corners of 135 degrees or more neither trap
etchant nor concentrate stress, and filling them made blobs (Y splits, zig-zags, a branch on a bend); 120 rather than 90 still covers a
hand-routed near-90 and a Y of 120. min_length_pct 25: a wedge cut by a pad or via to under a quarter of the width is a step, not a fillet
(a via 0.7 mm from a T); 50 % gave the same on the test board but drops a useful 0.35 mm wedge on a 0.8 mm track.
A wedge also stops short of other nets' copper by that copper's clearance: the fill would cut it there and leave a thin copper horn.
outdated() compares each wedge on the board with what the parameters draw today (a track moved or widened, a junction gone);
update_outdated() redoes only those.
shortcut: a junction is found per net+layer by exact coincident endpoints or an endpoint on another track's axis (1 um); two nodes
closer than a track width are handled one by one, and their wedges can overlap (same net, harmless).
"""
import fnmatch
import json
import math
import os
import sys
from collections import defaultdict

import pcbnew

NAME = "T-td"
AXIS_TOL = 1000  # nm: an endpoint this close to another track's axis is a junction
OVERLAP_MM = 0.001  # the wedge edges sit this far inside the tracks, so the pour merges with them (no hairline)
ARC_STEPS = 8
CELL_MM = 2.0  # copper_grid() cell
SHRINK_MM = 0.02  # a wedge over another net's clearance is shortened by this much per try
# min_fill_mm: the zone's minimum fill width, as KiCad's own teardrop zones: the fillet tapers to the track edge, and with the board
# minimum (0.127) the fill cut its tips off
DEFAULTS = {"length_pct": 300.0, "max_length_mm": 1.0, "min_length_mm": 0.05, "min_length_pct": 25.0, "max_angle_deg": 120.0, "min_fill_mm": 0.0254, "curved": True,
            "t_junctions": True, "crossings": True, "net": None, "netclass": None, "layer": None, "exclude_nets": "", "exclude_netclasses": []}


def shape_only(p=None):
    """settings(p) with every scope filter and exclusion off: the shape parameters over the whole board."""
    return {**settings(p), "net": None, "netclass": None, "layer": None, "t_junctions": True, "crossings": True, "exclude_nets": "",
            "exclude_netclasses": []}


def settings(p=None):
    """DEFAULTS overridden by the known keys of p."""
    return {**DEFAULTS, **{k: v for k, v in (p or {}).items() if k in DEFAULTS}}


def params_path(board_file):
    return os.path.splitext(board_file)[0] + ".teardrop_t.json"


def load(board_file):
    """The parameters saved next to the board (DEFAULTS where there is no file or key)."""
    path = params_path(board_file)
    return settings(json.load(open(path)) if os.path.exists(path) else None)


def save(board_file, p):
    with open(params_path(board_file), "w") as f:
        json.dump(settings(p), f, indent=1)


def junctions(board, tracks=None, p=None):
    """-> [{"key", "net", "layer", "node": (x, y) nm, "arms": [{"dir": (ux, uy), "width", "free"}]}] (width, free in mm).
    `tracks`: only the junctions touching one of these segments; p: the scope and filters of settings() (no p: every junction)."""
    mm = pcbnew.ToMM
    cfg = settings(p) if p is not None else None  # loops below reuse the name p
    excluded = [x.strip() for x in (cfg["exclude_nets"] or "").split(",") if x.strip()] if cfg else []
    wanted = None if tracks is None else {t.m_Uuid.AsString() for t in tracks}
    groups = defaultdict(list)
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_TRACE_T and t.GetNetCode():
            groups[(t.GetNetCode(), t.GetLayer())].append(t)
    pads = defaultdict(list)
    for pad in board.GetPads():
        pads[pad.GetNetCode()].append(pad)
    vias = defaultdict(list)
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            vias[t.GetNetCode()].append(t)
    out = []
    for (net, layer), segs in groups.items():
        name = segs[0].GetNetname()
        if cfg and (cfg["net"] and name != cfg["net"] or cfg["layer"] and board.GetLayerName(layer) != cfg["layer"]
                    or cfg["netclass"] and segs[0].GetNetClassName() != cfg["netclass"]
                    or any(fnmatch.fnmatchcase(name, x) for x in excluded) or segs[0].GetNetClassName() in (cfg["exclude_netclasses"] or [])):
            continue
        info = []
        for t in segs:
            a, e = (t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)
            if a != e:
                info.append((a, e, mm(t.GetWidth()), t.m_Uuid.AsString()))
        arms = defaultdict(list)  # node -> [(direction degrees, ux, uy, width, free, uuid)]
        for a, e, w, uid in info:
            length = math.dist(a, e)
            for p, q in ((a, e), (e, a)):
                arms[p].append((math.atan2(q[1] - p[1], q[0] - p[0]), (q[0] - p[0]) / length, (q[1] - p[1]) / length, w, mm(length), uid))
        for a, e, w, uid in info:  # a node on the axis of this track: it counts as two branches
            ex, ey = e[0] - a[0], e[1] - a[1]
            length = math.hypot(ex, ey)
            for pt in list(arms):
                if pt in (a, e):
                    continue
                u = ((pt[0] - a[0]) * ex + (pt[1] - a[1]) * ey) / (length * length)
                if not 0 < u < 1 or math.hypot(pt[0] - a[0] - u * ex, pt[1] - a[1] - u * ey) > AXIS_TOL:
                    continue  # on the axis, not just inside the width
                arms[pt].append((math.atan2(ey, ex), ex / length, ey / length, w, mm((1 - u) * length), uid))  # towards e: what is left to e
                arms[pt].append((math.atan2(-ey, -ex), -ex / length, -ey / length, w, mm(u * length), uid))
        for node, lst in arms.items():
            merged = {}  # one branch per direction (0.1 degree)
            for ang, ux, uy, w, free, uid in lst:
                k = round(math.degrees(ang) % 360, 1) % 360
                old = merged.get(k)
                merged[k] = (ang, ux, uy, max(w, old[3]) if old else w, max(free, old[4]) if old else free, (old[5] if old else frozenset()) | {uid})
            if len(merged) < 3 or cfg and not (cfg["t_junctions"] if len(merged) == 3 else cfg["crossings"]):
                continue
            P = pcbnew.VECTOR2I(*node)
            if any(p.IsOnLayer(layer) and p.HitTest(P, 1000) for p in pads[net]) or any(v.HitTest(P, 1000) for v in vias[net]):
                continue  # PTH/via/pad: its own teardrop
            for k, m in list(merged.items()):  # a branch is free up to the first pad/via of its net: the wedge stops at its edge
                merged[k] = m[:4] + (min(m[4], reach(node, m[1], m[2], m[4], pads[net], vias[net], layer)),) + m[5:]
            touched = set().union(*(m[5] for m in merged.values()))
            if wanted is not None and not (touched & wanted):
                continue
            out.append({"key": key(name, mm(node[0]), mm(node[1])), "net": segs[0].GetNet(), "layer": layer, "node": node,
                        "arms": [{"dir": (m[1], m[2]), "width": m[3], "free": m[4]} for _, m in sorted(merged.items())]})
    return out


def reach(node, ux, uy, free_mm, pads, vias, layer, step_mm=0.01):
    """How far (mm) from the node along (ux, uy), up to free_mm, before a pad on `layer` or a via of the net: past that edge the copper is
    the pad's (a wedge over it made acute notches with the pad edges)."""
    shapes = [p.GetEffectivePolygon(layer) for p in pads if p.IsOnLayer(layer)]  # the drawn copper: HitTest answers for a larger area
    discs = [(v.GetPosition().x, v.GetPosition().y, v.GetWidth(layer) / 2) for v in vias]
    for i in range(1, int(free_mm / step_mm) + 1):
        d = pcbnew.FromMM(i * step_mm)
        if any(sh.Contains(pcbnew.VECTOR2I(round(node[0] + ux * d), round(node[1] + uy * d))) for sh in shapes) or \
                any(math.dist((node[0] + ux * d, node[1] + uy * d), c[:2]) <= c[2] for c in discs):
            return round((i - 1) * step_mm, 3)  # the last point still outside: the wedge never steps onto the pad
    return free_mm


def key(net, x_mm, y_mm):
    return "%s@%.3f,%.3f" % (net, x_mm, y_mm)


def zone_key(z):
    """The junction key of a wedge zone: its net and its first outline vertex, the node."""
    v = z.Outline().Outline(0).CPoint(0)
    return key(z.GetNetname(), pcbnew.ToMM(v.x), pcbnew.ToMM(v.y))


def corner(node_mm, arm_a, arm_b, straight=False, p=None):
    """The corner from branch A to the next branch B (the following one in atan2 order). -> {"poly": zone outline [(x, y) mm]: node, A's axis
    level with PA, PA, the fillet arc (straight, or p["curved"] False: none), PB, B's axis level with PB; "c": where the two track edges facing
    the corner meet; "fillet": [C, PA, arc, PB]}, or None where the branches open more than max_angle_deg or a branch is too short for a
    wedge (min_length_mm, min_length_pct). p: settings()."""
    p = settings(p)
    straight = straight or not p["curved"]
    (ax, ay), (bx, by) = arm_a["dir"], arm_b["dir"]
    theta = math.atan2(ax * by - ay * bx, ax * bx + ay * by)  # signed angle A -> B in the y-down frame
    angle = round(math.degrees(theta), 1)  # rounded: three 120 degree corners of a Y gave 1 wedge of 3 with a 120 limit (float noise)
    if not 0 < angle <= p["max_angle_deg"] or angle >= 180:
        return None
    ha, hb = arm_a["width"] / 2 - OVERLAP_MM, arm_b["width"] / 2 - OVERLAP_MM
    na, nb = (-ay, ax), (by, -bx)  # the edge of A facing B and the edge of B facing A
    nx, ny = node_mm
    # node + na*ha + s*dA = node + nb*hb + t*dB
    rx, ry = nb[0] * hb - na[0] * ha, nb[1] * hb - na[1] * ha
    det = ax * -by + ay * bx
    s = (rx * -by + ry * bx) / det
    t = (ax * ry - ay * rx) / det
    c = (nx + na[0] * ha + s * ax, ny + na[1] * ha + s * ay)
    length = min(p["length_pct"] / 100 * min(arm_a["width"], arm_b["width"]), p["max_length_mm"], arm_a["free"] - s, arm_b["free"] - t)
    if length < max(p["min_length_mm"], p["min_length_pct"] / 100 * min(arm_a["width"], arm_b["width"])):
        return None
    pa = (c[0] + length * ax, c[1] + length * ay)
    pb = (c[0] + length * bx, c[1] + length * by)
    qa = (nx + (s + length) * ax, ny + (s + length) * ay)  # A's axis level with PA
    qb = (nx + (t + length) * bx, ny + (t + length) * by)
    if straight:
        arc = [pa, pb]
    else:
        r = length * math.tan(theta / 2)
        bis = (ax + bx, ay + by)
        bn = math.hypot(*bis)
        d = length / math.cos(theta / 2)
        o = (c[0] + bis[0] / bn * d, c[1] + bis[1] / bn * d)
        a0 = math.atan2(pa[1] - o[1], pa[0] - o[0])
        sweep = math.atan2(math.sin(math.atan2(pb[1] - o[1], pb[0] - o[0]) - a0), math.cos(math.atan2(pb[1] - o[1], pb[0] - o[0]) - a0))
        arc = [(o[0] + r * math.cos(a0 + sweep * i / ARC_STEPS), o[1] + r * math.sin(a0 + sweep * i / ARC_STEPS)) for i in range(ARC_STEPS + 1)]
    return {"poly": [node_mm, qa] + arc + [qb], "c": c, "fillet": [c] + arc}


def copper_grid(board):
    """Every track, via and pad by CELL_MM cell of its bounding box: {(i, k): [item]}, so plan() looks only at the copper next to a wedge."""
    cell = pcbnew.FromMM(CELL_MM)
    grid = defaultdict(list)
    for it in list(board.GetTracks()) + list(board.GetPads()):
        bb = it.GetBoundingBox()
        for i in range(bb.GetLeft() // cell, bb.GetRight() // cell + 1):
            for k in range(bb.GetTop() // cell, bb.GetBottom() // cell + 1):
                grid[(i, k)].append(it)
    return grid


def keepout(grid, poly_mm, net, layer, near):
    """The copper of other nets (and of no net) on `layer` near a wedge outline, each grown by its own clearance: the wedge stays out of it,
    since the fill would cut the wedge there and leave a thin copper horn (case 16 of test/). Zones are not in it: the wedges
    outrank the pours. ERROR_INSIDE: a track that sits exactly at the clearance must not count as an overlap. near (nm): how far around
    the wedge's box to look, the board's biggest clearance (a mains net class can ask for more than 1 mm). -> [SHAPE_POLY_SET]
    shortcut: only the item's own clearance (net class, one-item rules); a rule between two nets in the .kicad_dru is not seen, and there the
    fill still cuts the wedge."""
    cell = pcbnew.FromMM(CELL_MM)
    xs, ys = [pcbnew.FromMM(x) for x, _ in poly_mm], [pcbnew.FromMM(y) for _, y in poly_mm]
    walls, seen = [], set()
    for i in range((min(xs) - near) // cell, (max(xs) + near) // cell + 1):
        for k in range((min(ys) - near) // cell, (max(ys) + near) // cell + 1):
            for it in grid.get((i, k), ()):
                if id(it) in seen or it.GetNetCode() == net or not it.IsOnLayer(layer):
                    continue
                seen.add(id(it))
                shape = pcbnew.SHAPE_POLY_SET()
                it.TransformShapeToPolygon(shape, layer, it.GetOwnClearance(layer), pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
                walls.append(shape)
    return walls


def overlaps(poly_mm, walls):
    """Does the outline share more than 1 um2 with any of the walls?"""
    if not walls:
        return False
    wedge = pcbnew.SHAPE_POLY_SET()
    wedge.NewOutline()
    for x, y in poly_mm:
        wedge.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    for wall in walls:
        cut = pcbnew.SHAPE_POLY_SET(wedge)
        cut.BooleanIntersection(wall)
        if cut.Area() > 1e6:
            return True
    return False


def remove(board, keys=None):
    """Delete the "T-td" zones (only those of these junction keys, when given). -> how many."""
    zones = [z for z in board.Zones() if z.GetZoneName() == NAME and (keys is None or zone_key(z) in keys)]
    for z in zones:
        board.Remove(z)
    return len(zones)


def plan(board, tracks=None, straight=(), p=None, keys=None):
    """The corners add() would make, without touching the board (the dialog counts and previews them). keys: only these junctions.
    -> ([junction], [{"junction", "key", "net", "layer", "c", "poly"}])"""
    p = settings(p)
    js = [j for j in junctions(board, tracks, p) if keys is None or j["key"] in keys]
    grid = copper_grid(board) if js else None
    near = board.GetDesignSettings().GetBiggestClearanceValue()
    out = []
    for j in js:
        node = (pcbnew.ToMM(j["node"][0]), pcbnew.ToMM(j["node"][1]))
        arms = sorted(j["arms"], key=lambda a: math.atan2(a["dir"][1], a["dir"][0]))
        for i, a in enumerate(arms):
            b, flat = arms[(i + 1) % len(arms)], j["key"] in straight
            w = corner(node, a, b, flat, p)
            walls = keepout(grid, w["poly"], j["net"].GetNetCode(), j["layer"], near) if w else []
            while w and overlaps(w["poly"], walls):  # shorter until it keeps the clearance (a smaller wedge lies inside a larger one)
                w = corner(node, a, b, flat, {**p, "max_length_mm": math.dist(w["c"], w["poly"][2]) - SHRINK_MM})
            if w:
                out.append({"junction": j, "key": j["key"], "net": j["net"].GetNetname(), "layer": j["layer"], "c": w["c"], "poly": w["poly"]})
    return js, out


def remove_scope(board, tracks=None, p=None, keys=None):
    """Delete the wedges of the junctions in scope (tracks, filters, keys), the ones of excluded nets/classes, and the stale ones whose
    junction is gone. -> how many."""
    p = settings(p)
    scope = {j["key"] for j in junctions(board, tracks, p) if keys is None or j["key"] in keys}
    every = {j["key"] for j in junctions(board, tracks, shape_only(p))}
    kept = {j["key"] for j in junctions(board, tracks, {**shape_only(p), "exclude_nets": p["exclude_nets"],
                                                        "exclude_netclasses": p["exclude_netclasses"]})}
    alive = {j["key"] for j in junctions(board)}
    stale = {zone_key(z) for z in board.Zones() if z.GetZoneName() == NAME} - alive
    return remove(board, scope | (every - kept) | stale)


def add(board, tracks=None, straight=(), p=None, keys=None):
    """Re-make the wedges of the junctions in scope (tracks, filters of p, keys), one zone per corner; the wedges of other junctions stay,
    those of excluded nets go. `straight`: junction keys whose corners are triangles. Does not refill.
    -> [{"zone", "net", "layer", "c": C mm, "key", "poly"}]"""
    p = settings(p)
    remove_scope(board, tracks, p, keys)
    priority = 1 + max([z.GetAssignedPriority() for z in board.Zones() if not z.GetIsRuleArea() and not z.IsTeardropArea()] + [0])
    made = []
    for w in plan(board, tracks, straight, p, keys)[1]:
        j = w["junction"]
        z = pcbnew.ZONE(board)
        z.SetZoneName(NAME)
        z.SetLayer(j["layer"])
        z.SetNet(j["net"])
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetLocalClearance(pcbnew.FromMM(0))
        z.SetMinThickness(pcbnew.FromMM(p["min_fill_mm"]))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetAssignedPriority(priority + len(made))  # distinct: zones of nodes closer than a track width overlap, DRC flags equal priorities
        pts = pcbnew.VECTOR_VECTOR2I()
        for x, y in w["poly"]:
            pts.append(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        z.AddPolygon(pts)
        board.Add(z)
        made.append({"zone": z, "net": w["net"], "layer": j["layer"], "c": w["c"], "key": j["key"], "poly": w["poly"]})
    return made


def _um(points):
    return tuple((round(x / 1000), round(y / 1000)) for x, y in points)  # nm -> um, so rounding never decides


def outdated(board, p=None):
    """Wedges that no longer match their junction with the shape parameters of p (straight or curved both count as matching: a
    caller may make some straight to clear the DRC). -> {"gone": junction keys whose junction is gone, "changed": keys whose wedges differ}"""
    q = shape_only(p)
    existing = defaultdict(list)
    for z in board.Zones():
        if z.GetZoneName() == NAME:
            o = z.Outline().Outline(0)
            existing[zone_key(z)].append(_um((o.CPoint(i).x, o.CPoint(i).y) for i in range(o.PointCount())))
    js, curved = plan(board, p=q)
    straight = plan(board, straight={j["key"] for j in js}, p=q)[1]
    drawn = lambda corners, k: sorted(_um((pcbnew.FromMM(x), pcbnew.FromMM(y)) for x, y in w["poly"]) for w in corners if w["key"] == k)
    alive = {j["key"] for j in js}
    gone = {k for k in existing if k not in alive}
    changed = {k for k in existing if k in alive and sorted(existing[k]) not in (drawn(curved, k), drawn(straight, k))}
    return {"gone": gone, "changed": changed}


def update_outdated(board, p=None):
    """Remove the wedges whose junction is gone and redo the changed ones (curved). Does not refill. -> {"gone": n, "changed": n, "made"}"""
    o = outdated(board, p)
    remove(board, o["gone"])
    made = add(board, p=shape_only(p), keys=o["changed"]) if o["changed"] else []
    return {"gone": len(o["gone"]), "changed": len(o["changed"]), "made": made}


def area(poly):
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))) / 2


def selftest():
    board = pcbnew.BOARD()
    nets = {}

    def net(name):
        if name not in nets:
            nets[name] = pcbnew.NETINFO_ITEM(board, name, len(nets) + 1)
            board.Add(nets[name])
        return nets[name]

    def track(name, x0, y0, x1, y1, w=0.2):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x0), pcbnew.FromMM(y0)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        t.SetWidth(pcbnew.FromMM(w))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(net(name))
        board.Add(t)
        return t

    track("A", 10, 0, 10, 20)  # 90 degree T at (10,10)
    track("A", 10, 10, 20, 10)
    track("B", 30, 10, 50, 10)  # 45 degree branch at (40,10)
    track("B", 40, 10, 45, 15)
    track("C", 0, 40, 20, 40)  # cross at (10,40)
    track("C", 10, 30, 10, 40)
    track("C", 10, 40, 10, 50)
    fp = pcbnew.FOOTPRINT(board)  # T whose node is in a pad of its net
    pad = pcbnew.PAD(fp)
    pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.8), pcbnew.FromMM(0.8)))
    pad.SetLayerSet(pad.SMDMask())
    pad.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(30), pcbnew.FromMM(40)))
    pad.SetNet(net("D"))
    fp.Add(pad)
    board.Add(fp)
    track("D", 30, 30, 30, 50)
    track("D", 30, 40, 40, 40)
    track("E", 50, 40, 50, 60, 0.65)  # wide trunk, branch ends 0.2 mm beside the axis: HitTest would call it a junction
    track("E", 60, 50, 50.2, 50, 0.65)
    g_items = [track("G", 90, 10, 80, 10),  # one trunk segment through the node: 1.5 mm free to the left, 8.5 to the right
               track("G", 81.5, 10, 81.5, 15)]  # the branch meets it in the middle, at x 81.5
    fp_g = pcbnew.FOOTPRINT(board)  # and a pad of the net 1.2 mm to the right on the trunk: the wedge stops at its edge
    pad_g = pcbnew.PAD(fp_g)
    pad_g.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.6), pcbnew.FromMM(0.6)))
    pad_g.SetLayerSet(pad_g.SMDMask())
    pad_g.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(83.0), pcbnew.FromMM(10)))
    pad_g.SetNet(net("G"))
    fp_g.Add(pad_g)
    board.Add(fp_g)
    g_items.append(fp_g)
    track("F", 70, 10, 70, 20)  # branch of 0.25 mm, shorter than L = 0.3
    short = track("F", 70, 15, 70.25, 15)
    gnd = pcbnew.ZONE(board)
    gnd.SetLayer(pcbnew.F_Cu)
    gnd.SetNet(net("GND"))
    gnd.SetAssignedPriority(3)
    board.Add(gnd)

    js = {j["key"]: j for j in junctions(board)}
    g = js.pop("G@81.500,10.000")
    free = {a["dir"]: round(a["free"], 2) for a in g["arms"]}
    assert free[(-1.0, 0.0)] == 1.5 and free[(1.0, 0.0)] == 1.2, free  # each side its own length; the right one stops at the pad edge (83 - 0.3)
    node_g = (81.5, 10.0)
    arms_g = sorted(g["arms"], key=lambda a: math.atan2(a["dir"][1], a["dir"][0]))
    reach_x = max(x for w in (corner(node_g, a, arms_g[(i + 1) % 3]) for i, a in enumerate(arms_g)) if w for x, _ in w["poly"])
    assert reach_x <= 82.7 + 1e-6, reach_x  # no wedge over the pad
    for item in g_items:  # the rest of the test counts without G
        board.Remove(item)
    k_items = [track("K", 95, 10, 105, 10), track("K", 100, 10, 100, 15),  # a T whose lower right corner holds another net's track
               track("KO", 100.3, 10.25, 100.3, 14, 0.1)]
    k = {round(math.atan2(w["c"][1] - 10, w["c"][0] - 100), 1): w for w in plan(board, keys={"K@100.000,10.000"})[1]}
    wall = pcbnew.SHAPE_POLY_SET()  # a new BOARD has no clearance rules: GetOwnClearance is 0 here, so the wedge only stays off the copper
    k_items[2].TransformShapeToPolygon(wall, pcbnew.F_Cu, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
    length_k = {d: round(math.dist(w["c"], w["poly"][2]), 2) for d, w in k.items()}
    assert length_k[round(math.radians(135), 1)] == 0.6 and 0 < length_k[round(math.radians(45), 1)] < 0.6, length_k  # only the right one shrinks
    assert not overlaps(k[round(math.radians(45), 1)]["poly"], [wall]) and overlaps(
        corner((100.0, 10.0), {"dir": (1.0, 0.0), "width": 0.2, "free": 5.0}, {"dir": (0.0, 1.0), "width": 0.2, "free": 5.0})["poly"], [wall])
    for item in k_items:
        board.Remove(item)
    y = [{"dir": (math.cos(math.radians(a)), math.sin(math.radians(a))), "width": 0.2, "free": 5.0} for a in (-90, 30, 150)]
    assert all(corner((0.0, 0.0), y[i], y[(i + 1) % 3]) for i in range(3)), "a Y of 120 degrees: all 3 corners at the 120 limit"
    trunk_w, stub = {"dir": (1.0, 0.0), "width": 0.8, "free": 5.0}, {"dir": (0.0, 1.0), "width": 0.8, "free": 0.55}  # L 0.15 < 25 % of 0.8
    assert corner((0.0, 0.0), trunk_w, stub) is None and corner((0.0, 0.0), trunk_w, stub, p={"min_length_pct": 0})
    assert sorted(js) == ["A@10.000,10.000", "B@40.000,10.000", "C@10.000,40.000", "F@70.000,15.000"], sorted(js)
    assert len(js["C@10.000,40.000"]["arms"]) == 4

    def corners(key, straight=False, p=None):
        j = js[key]
        node = (pcbnew.ToMM(j["node"][0]), pcbnew.ToMM(j["node"][1]))
        arms = sorted(j["arms"], key=lambda a: math.atan2(a["dir"][1], a["dir"][0]))
        return [w for w in (corner(node, a, arms[(i + 1) % len(arms)], straight, p) for i, a in enumerate(arms)) if w]

    wa = corners("A@10.000,10.000")
    assert len(wa) == 2, wa  # 2 corners of 90 degrees; the straight side has none
    for w in wa:
        assert abs(abs(w["c"][0] - 10) - 0.1) < 0.005 and abs(abs(w["c"][1] - 10) - 0.1) < 0.005, w["c"]  # C: half a width from the node
        assert w["poly"][0] == (10.0, 10.0), w["poly"][0]  # the node is in the outline: a track end in the fill (not an island)
        assert 0 < area(w["fillet"]) < 0.6 ** 2 and area(w["poly"]) > area(w["fillet"]), (area(w["fillet"]), area(w["poly"]))
    assert len(corners("B@40.000,10.000")) == 1  # 135 degrees is over the 120 default: only the sharp corner
    a135, a45 = sorted(area(w["fillet"]) for w in corners("B@40.000,10.000", p={"max_angle_deg": 179}))  # the sharp corner holds more copper
    assert 0 < a135 < a45, (a135, a45)
    assert len(corners("C@10.000,40.000")) == 4
    for w in corners("F@70.000,15.000"):  # the 0.25 mm branch caps the wedge
        assert max(x for x, _ in w["poly"]) <= 70.25 + 1e-6, w["poly"]
    assert all(area(s_["fillet"]) > area(w["fillet"]) for s_, w in zip(corners("A@10.000,10.000", straight=True), wa))  # a triangle holds more
    made = add(board)
    assert sorted({m["key"] for m in made}) == sorted(js) and len(made) == 9, [m["key"] for m in made]  # one zone per corner
    assert all(m["zone"].GetAssignedPriority() >= 4 and m["zone"].GetZoneName() == NAME for m in made)
    assert len({m["zone"].GetAssignedPriority() for m in made}) == len(made)
    for m in made:  # corners of one junction meet on the axes: no shared area
        for o in made:
            if o is not m and o["key"] == m["key"]:
                cut = pcbnew.SHAPE_POLY_SET(m["zone"].Outline())
                cut.BooleanIntersection(o["zone"].Outline())
                assert cut.Area() < 1e6, (m["key"], cut.Area())  # under 1 um2
    wedges = lambda: sorted(zone_key(z) for z in board.Zones() if z.GetZoneName() == NAME)
    assert wedges() == sorted(m["key"] for m in made)  # zone_key: a zone's first vertex is its node
    only = add(board, tracks=[short])  # only the junction that touches the given segment is redone; the other 7 wedges stay
    assert [m["key"] for m in only] == ["F@70.000,15.000"] * 2 and len(wedges()) == 9, wedges()
    big = add(board, p={"net": "A", "length_pct": 500})  # a filter redoes only its junctions, with its own parameters
    assert [m["key"] for m in big] == ["A@10.000,10.000"] * 2 and len(wedges()) == 9
    assert all(area(b["poly"]) > area(m["poly"]) for b, m in zip(big, made[:2])), "500 % is a longer wedge than 300 %"
    assert len(add(board, p={"crossings": False})) == 5 and wedges().count("C@10.000,40.000") == 4, "the cross kept its wedges"
    assert len(plan(board, p={"layer": "B.Cu"})[1]) == 0 and len(plan(board, p={"netclass": "Default"})[1]) == 9
    n = len(list(board.Zones()))
    assert len(plan(board)[1]) == 9 and len(list(board.Zones())) == n, "plan() leaves the board as it is"
    straight_line = plan(board, p={"curved": False, "net": "A"})[1]
    assert all(len(w["poly"]) == 5 for w in straight_line), "node, axis, PA, PB, axis: no arc"
    add(board)
    assert outdated(board) == {"gone": set(), "changed": set()}, outdated(board)
    add(board, straight={"A@10.000,10.000"})  # a caller may make junctions straight for the DRC: still up to date
    assert outdated(board) == {"gone": set(), "changed": set()}, outdated(board)
    ex = add(board, p={"exclude_nets": "A, F*"})  # excluded nets lose their wedges, the rest is redone
    assert {m["key"] for m in ex} == {"B@40.000,10.000", "C@10.000,40.000"} and "A@10.000,10.000" not in wedges() \
        and "F@70.000,15.000" not in wedges(), wedges()
    assert not plan(board, p={"exclude_netclasses": ["Default"]})[1]
    add(board)
    branch_a = next(t for t in board.GetTracks() if t.GetNetname() == "A" and t.GetStart().x != t.GetEnd().x)
    branch_a.SetWidth(pcbnew.FromMM(0.3))  # a widened branch: A's wedges no longer fit it
    assert outdated(board) == {"gone": set(), "changed": {"A@10.000,10.000"}}, outdated(board)
    board.Remove(short)  # junction F is gone: its wedges are stale
    assert outdated(board) == {"gone": {"F@70.000,15.000"}, "changed": {"A@10.000,10.000"}}, outdated(board)
    u = update_outdated(board)
    assert (u["gone"], u["changed"], len(u["made"])) == (1, 1, 2) and outdated(board) == {"gone": set(), "changed": set()}, u
    branch_a.SetWidth(pcbnew.FromMM(0.2))  # F stays removed: the next add() drops its wedges as stale
    add(board)
    assert "F@70.000,15.000" not in wedges() and len(wedges()) == 7, wedges()
    assert remove(board, {"A@10.000,10.000"}) == 2 and remove(board) == 5 and not wedges()
    import tempfile
    with tempfile.TemporaryDirectory() as d:  # parameters saved next to the board, read back over DEFAULTS
        f = os.path.join(d, "x.kicad_pcb")
        assert load(f) == DEFAULTS
        save(f, {"length_pct": 250, "curved": False, "bogus": 1})
        assert load(f) == {**DEFAULTS, "length_pct": 250, "curved": False}
    print("selftest ok")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--selftest"]:
        selftest()
        sys.exit(0)
    assert len(args) == 2, __doc__
    board = pcbnew.LoadBoard(args[0])
    made = add(board, p=load(args[0]))
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(args[1])
    print("%d junctions, %d corners" % (len({m["key"] for m in made}), len(made)))
