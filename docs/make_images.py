"""Renders the README images from the test board (teste/gera.py): hero.png, cases.png, before.png, after.png and dialog.png in docs/.
"before" is the plugin with every corner up to 179 degrees, no minimum length and no clearance check (0.4.1); "after" is the defaults.
Run with KiCad's python (it opens the dialog for a moment):  $PY docs/make_images.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path[:0] = [REPO, os.path.join(REPO, "teste"), os.path.join(REPO, "mt_teardrop_t")]
import pcbnew  # noqa: E402
import wx  # noqa: E402

import dialog  # noqa: E402
import regressao  # noqa: E402
import teardrop_t  # noqa: E402

COMPARE = (5, 8, 12, 13, 16, 19)  # where the 0.4.2 rules change the result


def main():
    app = wx.App()
    board, _, casos = regressao.build()
    pick = lambda ids: [c for c in casos if c["id"] in ids]  # noqa: E731
    regressao.sheet(board, casos, os.path.join(HERE, "cases.png"))
    regressao.sheet(board, pick((2, 7, 9)), os.path.join(HERE, "hero.png"), r=2.0, px=300, cols=3)
    regressao.sheet(board, pick(COMPARE), os.path.join(HERE, "after.png"))
    keepout = teardrop_t.keepout
    teardrop_t.keepout = lambda *a: []  # no clearance check, as before 0.4.2
    old, _, _ = regressao.build({"max_angle_deg": 179, "min_length_pct": 0}, "antes")
    teardrop_t.keepout = keepout
    regressao.sheet(old, pick(COMPARE), os.path.join(HERE, "before.png"))

    bare = pcbnew.LoadBoard(os.path.join(regressao.OUT, "teste-t.kicad_pcb"))
    box = dialog.TeardropDialog(None, bare, teardrop_t)
    box.Show()
    for _ in range(20):
        app.Yield()
    w, h = box.GetClientSize()
    bmp = wx.Bitmap(w, h)
    dc = wx.MemoryDC(bmp)
    dc.Blit(0, 0, w, h, wx.ClientDC(box), 0, 0)
    dc.SelectObject(wx.NullBitmap)
    bmp.SaveFile(os.path.join(HERE, "dialog.png"), wx.BITMAP_TYPE_PNG)
    box.Destroy()
    print("images in", HERE)


if __name__ == "__main__":
    main()
