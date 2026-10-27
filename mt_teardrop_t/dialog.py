"""Parameter dialog of the T-junction teardrop plugin: live preview of a sample T drawn with the core's own corner(), a live count
from core.plan(), and an optional "Preview on board" that really applies the action (debounced) and is undone by Cancel.
The core is passed in (the plugin loads it by file path, see __init__.core()); this file never imports it by name."""
import math

import pcbnew
import wx

BG, TRACK, WEDGE = wx.Colour(0x1D, 0x2B, 0x1D), wx.Colour(0xC8, 0x34, 0x34), wx.Colour(0xF2, 0xA9, 0x3B)
PREVIEW_DELAY_MS = 400
VIEW_MM = 6.0  # width of the sample view
# key -> (label, low, high, unit); a value outside [low, high] is ignored (the last valid one stays) and flagged in red
RANGES = {"length_pct": (50.0, 600.0), "max_length_mm": (0.05, 10.0), "min_length_mm": (0.0, 5.0), "min_length_pct": (0.0, 200.0), "max_angle_deg": (1.0, 180.0),
          "min_fill_mm": (0.001, 1.0), "sample_w": (0.05, 2.0)}


def snapshot(zone):
    """What core.add() sets on a T-td zone, as plain data: Clone() and re-adding removed zone objects crash or leave dead SWIG wrappers."""
    pts = zone.Outline().Outline(0)
    return {"layer": zone.GetLayer(), "net": zone.GetNetCode(), "priority": zone.GetAssignedPriority(), "min": zone.GetMinThickness(),
            "name": zone.GetZoneName(), "pts": [(pts.CPoint(i).x, pts.CPoint(i).y) for i in range(pts.PointCount())]}


def rebuild(board, snap):
    z = pcbnew.ZONE(board)
    z.SetZoneName(snap["name"])
    z.SetLayer(snap["layer"])
    z.SetNetCode(snap["net"])
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetLocalClearance(0)
    z.SetMinThickness(snap["min"])
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetAssignedPriority(snap["priority"])
    pts = pcbnew.VECTOR_VECTOR2I()
    for x, y in snap["pts"]:
        pts.append(pcbnew.VECTOR2I(x, y))
    z.AddPolygon(pts)
    board.Add(z)


def draw_preview(gc, width, height, core, p, branch45=False, track_w=0.25):
    """Draws the sample T into gc (wx.GraphicsContext) and returns L in mm of its first corner (None when no wedge fits).
    Trunk horizontal, branch down (or at 45 degrees), every corner from core.corner() with the current parameters."""
    gc.DisableOffset()  # macOS shifts odd-width lines half a pixel: the branch covered more of one fillet than of the other
    gc.SetBrush(wx.Brush(BG))
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.DrawRectangle(0, 0, width, height)
    scale = width / VIEW_MM
    ox, oy = width / 2, height * 0.38
    ang = math.radians(45) if branch45 else math.radians(90)
    free = 2.5
    dirs = [(1.0, 0.0), (math.cos(ang), math.sin(ang)), (-1.0, 0.0)]  # sorted by atan2: right, branch, left
    arms = [{"dir": d, "width": track_w, "free": free} for d in dirs]
    to_px = lambda x, y: (ox + x * scale, oy + y * scale)
    length = None
    gc.SetBrush(wx.Brush(WEDGE))
    for i, a in enumerate(arms):
        w = core.corner((0.0, 0.0), a, arms[(i + 1) % 3], False, p)
        if not w:
            continue
        if length is None:
            length = math.dist(w["c"], w["fillet"][1])
        path = gc.CreatePath()
        for k, pt in enumerate(w["poly"]):
            (path.MoveToPoint if k == 0 else path.AddLineToPoint)(*to_px(*pt))
        path.CloseSubpath()
        gc.FillPath(path)
    pen = wx.Pen(TRACK, max(1, int(round(track_w * scale))))
    pen.SetCap(wx.CAP_ROUND)
    gc.SetPen(pen)
    for d in dirs:
        gc.StrokeLine(ox, oy, *to_px(d[0] * free, d[1] * free))
    if length is not None:
        gc.SetFont(wx.Font(wx.FontInfo(10)), wx.Colour(235, 235, 235))
        gc.DrawText("L = %.2f mm" % length, width - 105, 8)
    return length


class Preview(wx.Panel):
    def __init__(self, parent, owner):
        super().__init__(parent, size=(360, 280))
        self.owner = owner
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)

    def on_paint(self, _):
        dc = wx.AutoBufferedPaintDC(self)
        gc = wx.GraphicsContext.Create(dc)
        w, h = self.GetClientSize()
        draw_preview(gc, w, h, *self.owner.preview_args())


class TeardropDialog(wx.Dialog):
    def __init__(self, parent, board, core):
        super().__init__(parent, title="T-junction teardrops")
        self.board, self.core = board, core
        self.file = board.GetFileName()
        self.p = core.load(self.file) if self.file else core.settings()
        self.sample_w = 0.25
        self.values = {k: self.p[k] for k in RANGES if k in self.p}
        self.values["sample_w"] = self.sample_w
        self.selected = [t for t in board.GetTracks() if t.IsSelected() and t.Type() == pcbnew.PCB_TRACE_T]
        self.baseline = [snapshot(z) for z in board.Zones() if z.GetZoneName() == core.NAME]
        self.touched = False
        self.timer = None
        self.fields, self.errors, self.filters = {}, {}, {}
        self.build()
        self.refresh_stale()
        self.on_change()

    # ---- layout
    def field(self, parent, grid, key, label, unit=""):
        grid.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
        box = wx.TextCtrl(parent, value="%g" % self.values[key], size=(70, -1))
        err = wx.StaticText(parent, label="")
        err.SetForegroundColour(wx.RED)
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(box, 0, wx.ALIGN_CENTER_VERTICAL)
        row.Add(wx.StaticText(parent, label=" " + unit), 0, wx.ALIGN_CENTER_VERTICAL)
        row.Add(err, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 6)
        grid.Add(row)
        box.Bind(wx.EVT_TEXT, lambda _: self.on_change())
        self.fields[key], self.errors[key] = box, err

    def choices(self, kind):
        tracks = [t for t in self.board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
        if kind == "net":
            names = {t.GetNetname() for t in tracks if t.GetNetCode()}
        elif kind == "netclass":
            names = {t.GetNetClassName() for t in tracks if t.GetNetCode()}
        else:
            names = {self.board.GetLayerName(t.GetLayer()) for t in tracks}
        if self.p[kind]:
            names.add(self.p[kind])
        return sorted(names)

    def build(self):
        p = self.p
        left, right = wx.BoxSizer(wx.VERTICAL), wx.BoxSizer(wx.VERTICAL)
        self.preview = Preview(self, self)
        left.Add(self.preview, 1, wx.EXPAND)
        self.shape = wx.RadioBox(self, choices=["Curved", "Line"], majorDimension=2)
        self.shape.SetSelection(0 if p["curved"] else 1)
        self.branch = wx.RadioBox(self, choices=["90° branch", "45° branch"], majorDimension=2)
        for c in (self.shape, self.branch):
            c.Bind(wx.EVT_RADIOBOX, lambda _: self.on_change())
            left.Add(c, 0, wx.TOP, 6)
        grid = wx.FlexGridSizer(2, 6, 6)
        self.field(self, grid, "length_pct", "Length (% of narrower track)")
        self.field(self, grid, "max_length_mm", "Maximum length", "mm")
        self.field(self, grid, "sample_w", "Preview track width", "mm")
        left.Add(grid, 0, wx.TOP, 6)

        self.mode = wx.RadioBox(self, label="Working mode", choices=["Add or update", "Remove"], majorDimension=1)
        self.objects = wx.RadioBox(self, label="Objects", choices=["All", "Only selected tracks"], majorDimension=1)
        for c in (self.mode, self.objects):
            c.Bind(wx.EVT_RADIOBOX, lambda _: self.on_change())
            right.Add(c, 0, wx.EXPAND | wx.BOTTOM, 6)
        scope = wx.StaticBoxSizer(wx.VERTICAL, self, "Scope")
        self.t_junctions = wx.CheckBox(self, label="T junctions")
        self.crossings = wx.CheckBox(self, label="Crossings (4+ branches)")
        for c, k in ((self.t_junctions, "t_junctions"), (self.crossings, "crossings")):
            c.SetValue(p[k])
            c.Bind(wx.EVT_CHECKBOX, lambda _: self.on_change())
            scope.Add(c, 0, wx.ALL, 3)
        right.Add(scope, 0, wx.EXPAND | wx.BOTTOM, 6)
        filt = wx.StaticBoxSizer(wx.VERTICAL, self, "Filter")
        for kind, label in (("net", "Net"), ("layer", "Layer"), ("netclass", "Net class")):
            row = wx.BoxSizer(wx.HORIZONTAL)
            check = wx.CheckBox(self, label=label, size=(90, -1))
            choice = wx.Choice(self, choices=self.choices(kind))
            if p[kind]:
                check.SetValue(True)
                choice.SetStringSelection(p[kind])
            elif choice.GetCount():
                choice.SetSelection(0)
            row.Add(check, 0, wx.ALIGN_CENTER_VERTICAL)
            row.Add(choice, 1, wx.EXPAND)
            check.Bind(wx.EVT_CHECKBOX, lambda _: self.on_change())
            choice.Bind(wx.EVT_CHOICE, lambda _: self.on_change())
            self.filters[kind] = (check, choice)
            filt.Add(row, 0, wx.EXPAND | wx.ALL, 3)
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label="Exclude nets", size=(90, -1)), 0, wx.ALIGN_CENTER_VERTICAL)
        self.exclude_nets = wx.TextCtrl(self, value=p["exclude_nets"] or "")
        self.exclude_nets.SetHint("USB_D*, RF_*")
        self.exclude_nets.Bind(wx.EVT_TEXT, lambda _: self.on_change())
        row.Add(self.exclude_nets, 1, wx.EXPAND)
        filt.Add(row, 0, wx.EXPAND | wx.ALL, 3)
        filt.Add(wx.StaticText(self, label="Exclude net classes"), 0, wx.LEFT | wx.TOP, 3)
        names = sorted(set(self.choices("netclass")) | set(p["exclude_netclasses"] or []))
        self.exclude_classes = wx.CheckListBox(self, choices=names, size=(-1, 60))
        self.exclude_classes.SetCheckedStrings([n for n in p["exclude_netclasses"] or [] if n in names])
        self.exclude_classes.Bind(wx.EVT_CHECKLISTBOX, lambda _: self.on_change())
        filt.Add(self.exclude_classes, 0, wx.EXPAND | wx.ALL, 3)
        right.Add(filt, 0, wx.EXPAND | wx.BOTTOM, 6)
        adv = wx.StaticBoxSizer(wx.VERTICAL, self, "Advanced")
        grid = wx.FlexGridSizer(2, 6, 6)
        self.field(adv.GetStaticBox(), grid, "max_angle_deg", "Max corner angle", "°")
        self.field(adv.GetStaticBox(), grid, "min_length_mm", "Min length", "mm")
        self.field(adv.GetStaticBox(), grid, "min_length_pct", "Min length (% of width)", "%")
        self.field(adv.GetStaticBox(), grid, "min_fill_mm", "Min fill width", "mm")
        adv.Add(grid, 0, wx.ALL, 3)
        right.Add(adv, 0, wx.EXPAND)

        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(left, 0, wx.ALL, 10)
        top.Add(right, 1, wx.EXPAND | wx.TOP | wx.RIGHT | wx.BOTTOM, 10)
        self.count = wx.StaticText(self, label="")
        self.live = wx.CheckBox(self, label="Preview on board")
        self.live.Bind(wx.EVT_CHECKBOX, lambda _: self.schedule(0))
        self.ok = wx.Button(self, wx.ID_OK, "Apply")
        self.cancel = wx.Button(self, wx.ID_CANCEL, "Cancel")
        self.ok.Bind(wx.EVT_BUTTON, lambda _: self.on_apply())
        self.cancel.Bind(wx.EVT_BUTTON, lambda _: self.on_cancel())
        self.Bind(wx.EVT_CLOSE, lambda _: self.on_cancel())
        self.stale = wx.StaticText(self, label="")
        self.update_button = wx.Button(self, label="Update out-of-date")
        self.update_button.Bind(wx.EVT_BUTTON, lambda _: self.on_update())
        status = wx.BoxSizer(wx.HORIZONTAL)
        status.Add(self.stale, 1, wx.ALIGN_CENTER_VERTICAL)
        status.Add(self.update_button, 0)
        bottom = wx.BoxSizer(wx.HORIZONTAL)
        bottom.Add(self.count, 1, wx.ALIGN_CENTER_VERTICAL)
        bottom.Add(self.live, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)
        bottom.Add(self.ok)
        bottom.Add(self.cancel, 0, wx.LEFT, 6)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(top, 1, wx.EXPAND)
        outer.Add(status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        outer.Add(bottom, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.SetSizerAndFit(outer)

    # ---- values
    def read_fields(self):
        for key, box in self.fields.items():
            low, high = RANGES[key]
            try:
                v = float(box.GetValue().replace(",", "."))
                ok = low <= v <= high and math.isfinite(v)
            except ValueError:
                ok = False
            self.errors[key].SetLabel("" if ok else "%g to %g" % (low, high))
            if ok:
                self.values[key] = v

    def params(self):
        """The settings of the current controls (an invalid field keeps its last valid value)."""
        p = {k: self.values[k] for k in RANGES if k != "sample_w"}
        p.update(curved=self.shape.GetSelection() == 0, t_junctions=self.t_junctions.GetValue(), crossings=self.crossings.GetValue())
        p.update(exclude_nets=self.exclude_nets.GetValue().strip(), exclude_netclasses=list(self.exclude_classes.GetCheckedStrings()))
        for kind, (check, choice) in self.filters.items():
            p[kind] = choice.GetStringSelection() if check.GetValue() and choice.GetSelection() >= 0 else None
        return self.core.settings(p)

    def tracks(self):
        return self.selected if self.objects.GetSelection() == 1 else None

    def preview_args(self):
        return self.core, self.params(), self.branch.GetSelection() == 1, self.values["sample_w"]

    def counts(self):
        """-> (corners or wedges, junctions) the action would add / remove, with the current controls."""
        p, tracks = self.params(), self.tracks()
        if self.mode.GetSelection() == 0:
            _, corners = self.core.plan(self.board, tracks, (), p)
            return len(corners), len({c["key"] for c in corners})
        keys = {j["key"] for j in self.core.junctions(self.board, tracks, p)}
        alive = {j["key"] for j in self.core.junctions(self.board)}
        gone = keys | ({self.core.zone_key(z) for z in self.board.Zones() if z.GetZoneName() == self.core.NAME} - alive)
        zones = [z for z in self.board.Zones() if z.GetZoneName() == self.core.NAME and self.core.zone_key(z) in gone]
        return len(zones), len({self.core.zone_key(z) for z in zones})

    def on_change(self):
        self.read_fields()
        self.preview.Refresh()
        n, m = self.counts()
        if self.mode.GetSelection() == 0:
            self.count.SetLabel("%d corners in %d junctions will be added" % (n, m))
        else:
            self.count.SetLabel("%d wedges will be removed" % n)
        if self.live.GetValue():
            self.schedule(PREVIEW_DELAY_MS)

    # ---- board
    def schedule(self, delay):
        if self.timer:
            self.timer.Stop()
        if self.live.GetValue():
            self.timer = wx.CallLater(max(delay, 1), self.apply_to_board)
        elif self.touched:
            self.restore()

    def restore(self):
        """The board as it was when the dialog opened (as far as T-td zones go)."""
        self.core.remove(self.board)
        for snap in self.baseline:
            rebuild(self.board, snap)
        pcbnew.ZONE_FILLER(self.board).Fill(self.board.Zones())
        pcbnew.Refresh()
        self.touched = False

    def act(self):
        self.core.remove(self.board)
        for snap in self.baseline:
            rebuild(self.board, snap)
        p, tracks = self.params(), self.tracks()
        if self.mode.GetSelection() == 0:
            self.core.add(self.board, tracks, (), p)
        else:
            self.core.remove_scope(self.board, tracks, p)
        pcbnew.ZONE_FILLER(self.board).Fill(self.board.Zones())
        pcbnew.Refresh()
        self.touched = True

    def apply_to_board(self):
        self.timer = None
        self.act()

    def finish(self, code):
        if self.timer:
            self.timer.Stop()
            self.timer = None
        if self.IsModal():
            self.EndModal(code)

    def refresh_stale(self):
        """Wedges that no longer match their junction, against the parameters saved with the board (the current ones without a file)."""
        saved = self.core.load(self.file) if self.file else self.params()
        old = self.core.outdated(self.board, saved)
        keys = old["gone"] | old["changed"]
        n = len([z for z in self.board.Zones() if z.GetZoneName() == self.core.NAME and self.core.zone_key(z) in keys])
        if n:
            self.stale.SetLabel("%d wedges out of date (%d junctions gone, %d changed)" % (n, len(old["gone"]), len(old["changed"])))
        else:
            self.stale.SetLabel("All wedges up to date")
        self.update_button.Show(n > 0)
        self.Layout()
        return n

    def on_update(self):
        if self.touched:
            self.restore()  # drop the board preview: the update works on the real wedges
        self.core.update_outdated(self.board, self.params())
        pcbnew.ZONE_FILLER(self.board).Fill(self.board.Zones())
        pcbnew.Refresh()
        self.baseline = [snapshot(z) for z in self.board.Zones() if z.GetZoneName() == self.core.NAME]
        self.refresh_stale()
        self.on_change()

    def on_apply(self):
        self.act()
        if self.file:
            self.core.save(self.file, self.params())
        self.baseline = [snapshot(z) for z in self.board.Zones() if z.GetZoneName() == self.core.NAME]
        self.touched = False
        self.refresh_stale()
        self.finish(wx.ID_OK)

    def on_cancel(self):
        if self.timer:
            self.timer.Stop()
            self.timer = None
        if self.touched:
            self.restore()
        self.finish(wx.ID_CANCEL)
