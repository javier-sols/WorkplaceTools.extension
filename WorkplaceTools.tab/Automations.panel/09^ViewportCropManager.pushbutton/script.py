# -*- coding: utf-8 -*-
"""
ViewportCropManager
Batch manager for viewport crop region line graphic overrides across sheets.
Modeless WPF spreadsheet UI: parent/child sheet grouping, three-state selection,
click/ctrl/shift row selection, batch Lineweight/Color/Line Pattern editing with
multi-row propagation, single-transaction Apply, sentinel-based Reset.
Verified against Revit 2025.3 (live API probes + headless round-trips).
"""

__title__ = "ViewportCrop\nManager"
__doc__ = "Batch override viewport crop region line properties (lineweight, color, line pattern) across sheets. Select rows (click/ctrl/shift), edit with multi-row propagation, Apply in one transaction. Reset uses API sentinels to clear merge-aware overrides."
__persistentengine__ = True

import traceback
import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")

from System import Action
from System.Windows import (Application, Window, ResizeMode, GridLength,
                            GridUnitType, Thickness, MessageBox,
                            HorizontalAlignment, VerticalAlignment,
                            FontWeights, CornerRadius)
from System.Windows.Controls import (Grid, StackPanel, ScrollViewer, CheckBox,
                                     ComboBox, Button, TextBlock, Border,
                                     ColumnDefinition, RowDefinition,
                                     Orientation, ScrollBarVisibility)
from System.Windows.Media import (SolidColorBrush, Color as MColor,
                                  Colors as WColors, VisualTreeHelper,
                                  FontFamily)
from System.Windows.Input import Keyboard, ModifierKeys, Cursors
from System.Windows.Forms import ColorDialog, DialogResult
from System.Drawing import Color as DColor
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent
from Autodesk.Revit.DB import (Transaction, FilteredElementCollector,
                               ElementId, Color, OverrideGraphicSettings,
                               View, ViewSheet, Viewport, LinePatternElement)

SKIP_VT = set(["Schedule", "Legend", "DrawingSheet", "Report", "undefined",
               "ProjectBrowser", "SystemBrowser"])

SEL_BG = SolidColorBrush(MColor.FromRgb(0xB4, 0xD7, 0xF7))
GRAY_BG = SolidColorBrush(MColor.FromRgb(0xC8, 0xCE, 0xD6))
TRANS = SolidColorBrush(MColor.FromArgb(0, 0, 0, 0))
DEF = "(default)"

COL_W = [18, 62, 78, 185, 95, 225, 155, 90, 88, 160, 150]
HEADERS = ["", "Sel", "Sheet #", "Sheet Name", "View Type", "View Name",
           "Title on Sheet", "Lineweight", "Color", "Line Pattern", "Current"]

VIEWPORT_CROP_MANAGER_STATE = {
    "win": None, "rows": [], "mode": None, "busy": False, "error": None,
    "type_filter": "All", "show_selected_only": False,
    "pattern_map": {}, "pattern_rev": {}, "pattern_order": [],
    "updating": False, "event": None, "handler": None, "callback": None,
    "ensure_visible": True, "status": "Ready.", "_editing": False,
}
st = VIEWPORT_CROP_MANAGER_STATE


def uni(cp):
    """Runtime glyph builder (IronPython 2 chr() is capped at U+00FF)."""
    try:
        return unichr(cp)
    except NameError:
        return chr(cp)

ARROW_EXP = uni(0x25BC)
ARROW_COL = uni(0x25BA)
WIN_TITLE = "JMS Tools - ViewportCropManager"


class ViewportCropManagerRow(object):
    def __init__(self):
        self.is_parent = False; self.selected = False
        self.sheet_id = None; self.sheet_num = ""; self.sheet_name = ""
        self.view_id = None; self.viewport_id = None
        self.view_type = ""; self.view_name = ""
        self.title_on_sheet = ""; self.crop_id = None
        self.weight = None; self.rgb = None
        self.pattern_id = None; self.pattern_name = None
        self.cur_weight = None; self.cur_rgb = None; self.cur_pattern_id = None
        self.status = ""
        self.parent = None; self.children = []; self.expanded = True


def resolve_crop(doc, view):
    """Hidden per-view crop-region element resolver (verified Revit 2025.3).

    The crop boundary is NOT a collectible category element and its category
    refuses per-view overrides. Revit keeps a hidden internal element instead:
    raw 'Element' class, Name == view.Name, Category 'Views' (or None on plan
    views), visible only to the view-scoped collector.
    """
    vname = view.Name
    for e in FilteredElementCollector(doc, view.Id):
        try:
            if e.GetType().Name != "Element" or e.Name != vname:
                continue
            cat = e.Category
            if cat is None or cat.Name == "Views":
                return e
        except Exception:
            pass
    return None


def get_title(vp):
    try:
        for p in vp.Parameters:
            if p.Definition.Name == "Title on Sheet":
                return p.AsString() or ""
    except Exception:
        pass
    return ""


def read_current(view, crop):
    if crop is None:
        return (None, None, None)
    ovr = view.GetElementOverrides(crop.Id)
    w = ovr.ProjectionLineWeight
    cw = None if w == OverrideGraphicSettings.InvalidPenNumber else w
    try:
        c = ovr.ProjectionLineColor
        crgb = (c.Red, c.Green, c.Blue)
    except Exception:
        crgb = None
    pid = ovr.ProjectionLinePatternId.IntegerValue
    cpid = None if pid == -1 else pid
    return (cw, crgb, cpid)


def sheet_viewports(doc, sheet):
    sid = sheet.Id.IntegerValue
    return [vp for vp in FilteredElementCollector(doc).OfClass(Viewport).ToElements()
            if vp.SheetId.IntegerValue == sid]


def collect_rows(doc, uidoc, mode, st):
    st["pattern_map"] = {}; st["pattern_rev"] = {}; st["pattern_order"] = []
    for p in FilteredElementCollector(doc).OfClass(LinePatternElement).ToElements():
        st["pattern_map"][p.Id.IntegerValue] = p.Name
        st["pattern_rev"][p.Name] = p.Id.IntegerValue
        st["pattern_order"].append(p.Name)
    st["pattern_order"].sort()

    targets = []; seen = set()

    def add_vp(vp):
        i = vp.Id.IntegerValue
        if i in seen:
            return
        seen.add(i); targets.append(vp)

    if mode == "selection":
        for eid in uidoc.Selection.GetElementIds():
            el = doc.GetElement(eid)
            if el is None:
                continue
            tn = el.GetType().Name
            if tn == "ViewSheet":
                for vp in sheet_viewports(doc, el):
                    add_vp(vp)
            elif tn == "Viewport":
                add_vp(el)
            elif tn.startswith("View"):
                for vp in FilteredElementCollector(doc).OfClass(Viewport).ToElements():
                    if vp.ViewId.IntegerValue == el.Id.IntegerValue:
                        add_vp(vp)
    else:
        for vp in FilteredElementCollector(doc).OfClass(Viewport).ToElements():
            add_vp(vp)

    by_sheet = {}
    for vp in targets:
        view = doc.GetElement(vp.ViewId)
        if view is None:
            continue
        vt = str(view.ViewType)
        if vt in SKIP_VT:
            continue
        by_sheet.setdefault(vp.SheetId.IntegerValue, []).append((vp, view, vt))

    rows = []

    def sheetnum(sid):
        try:
            return doc.GetElement(ElementId(sid)).SheetNumber or ""
        except Exception:
            return ""

    for sid in sorted(by_sheet.keys(), key=sheetnum):
        sheet = doc.GetElement(ElementId(sid))
        pr = ViewportCropManagerRow()
        pr.is_parent = True; pr.sheet_id = sid
        pr.sheet_num = sheet.SheetNumber; pr.sheet_name = sheet.Name
        pr.expanded = True; pr.children = []
        for vp, view, vt in sorted(by_sheet[sid], key=lambda t: t[1].Name):
            crop = resolve_crop(doc, view)
            cw, crgb, cpid = read_current(view, crop)
            ch = ViewportCropManagerRow()
            ch.parent = pr
            ch.view_id = view.Id.IntegerValue
            ch.viewport_id = vp.Id.IntegerValue
            ch.view_type = vt; ch.view_name = view.Name
            ch.title_on_sheet = get_title(vp)
            ch.crop_id = crop.Id.IntegerValue if crop else None
            ch.cur_weight = cw; ch.cur_rgb = crgb; ch.cur_pattern_id = cpid
            ch.weight = cw; ch.rgb = crgb; ch.pattern_id = cpid
            ch.pattern_name = st["pattern_map"].get(cpid) if cpid else None
            ch.status = "" if crop is not None else "no crop element"
            pr.children.append(ch)
        rows.append(pr)
    st["rows"] = rows
    st["status"] = "Loaded {0} viewports on {1} sheets.".format(len(targets), len(rows))


def apply_overrides(doc, st, reset_mode):
    tname = ("ViewportCropManager: Batch Reset Crop Region Overrides" if reset_mode
             else "ViewportCropManager: Batch Override Crop Region Lines")
    t = Transaction(doc, tname)
    t.Start()
    applied = 0
    try:
        for pr in list(st["rows"]):
            for ch in list(pr.children):
                if not ch.selected:
                    continue
                view = doc.GetElement(ElementId(ch.view_id))
                if view is None:
                    ch.status = "view missing"; continue
                if st["ensure_visible"] and not reset_mode:
                    try:
                        if not view.CropBoxVisible:
                            view.CropBoxVisible = True
                    except Exception:
                        pass
                crop = resolve_crop(doc, view)
                if crop is None:
                    ch.status = "no crop element"; continue
                ch.crop_id = crop.Id.IntegerValue
                if reset_mode:
                    ogs = OverrideGraphicSettings()
                    ogs.SetProjectionLineWeight(OverrideGraphicSettings.InvalidPenNumber)
                    ogs.SetProjectionLineColor(Color.InvalidColorValue)
                    ogs.SetProjectionLinePatternId(ElementId.InvalidElementId)
                else:
                    if (ch.weight is None and ch.rgb is None
                            and ch.pattern_id is None):
                        ch.status = "nothing set"; continue
                    ogs = OverrideGraphicSettings()
                    if ch.weight is not None:
                        ogs.SetProjectionLineWeight(ch.weight)
                    if ch.rgb is not None:
                        ogs.SetProjectionLineColor(
                            Color(ch.rgb[0], ch.rgb[1], ch.rgb[2]))
                    if ch.pattern_id is not None:
                        ogs.SetProjectionLinePatternId(ElementId(ch.pattern_id))
                view.SetElementOverrides(crop.Id, ogs)
                cw, crgb, cpid = read_current(view, crop)
                ch.cur_weight = cw; ch.cur_rgb = crgb; ch.cur_pattern_id = cpid
                ch.status = "reset" if reset_mode else "applied"
                applied += 1
        t.Commit()
    except Exception:
        t.RollBack()
        raise
    st["status"] = ("Reset {0} viewports to default." if reset_mode
                    else "Applied overrides to {0} viewports.").format(applied)


class ViewportCropManagerHandler(IExternalEventHandler):
    def __init__(self, st):
        self.st = st

    def Execute(self, app):
        st = self.st
        st["error"] = None
        try:
            uidoc = app.ActiveUIDocument
            doc = uidoc.Document
            mode = st["mode"]
            if mode == "load_all":
                collect_rows(doc, uidoc, "all", st)
            elif mode == "load_selection":
                collect_rows(doc, uidoc, "selection", st)
            elif mode == "apply":
                apply_overrides(doc, st, False)
            elif mode == "reset":
                apply_overrides(doc, st, True)
        except Exception as ex:
            st["error"] = str(ex)
        st["busy"] = False
        cb = st.get("callback"); win = st.get("win")
        if cb is not None and win is not None:
            try:
                win.Dispatcher.BeginInvoke(Action(cb))
            except Exception:
                pass

    def GetName(self):
        return "ViewportCropManager"


def mods():
    try:
        m = int(Keyboard.Modifiers)
    except Exception:
        m = 0
    return ((m & int(ModifierKeys.Control)) != 0, (m & int(ModifierKeys.Shift)) != 0)


def parent_state_for(pr):
    kids = pr.children
    if not kids:
        return False
    n = len([ch for ch in kids if ch.selected])
    if n == 0:
        return False
    if n == len(kids):
        return True
    return None


def sync_parent_cb(pr):
    ui = st["_row_ui"].get(id(pr))
    if ui and ui.get("parent_cb") is not None:
        ui["parent_cb"].IsChecked = parent_state_for(pr)


def update_row_visual(c):
    ui = st["_row_ui"].get(id(c))
    if not ui:
        return
    if ui.get("border") is not None:
        ui["border"].Background = SEL_BG if c.selected else TRANS
    if ui.get("cb") is not None:
        ui["cb"].IsChecked = bool(c.selected)


def update_sel_count():
    tot = 0; n = 0
    for p in st["rows"]:
        for ch in p.children:
            tot += 1
            if ch.selected:
                n += 1
    if st.get("sel_tb") is not None:
        st["sel_tb"].Text = "{0} of {1} viewports selected".format(n, tot)


def row_click(c, ctrl=False, shift=False):
    order = st["_vis_children"]
    if c not in order:
        return
    if ctrl:
        c.selected = not c.selected
        st["_anchor"] = c
    elif shift:
        anchor = st.get("_anchor")
        if anchor is None or anchor not in order:
            for p in st["rows"]:
                for ch in p.children:
                    ch.selected = False
            c.selected = True
            st["_anchor"] = c
        else:
            i1 = order.index(anchor); i2 = order.index(c)
            lo = min(i1, i2); hi = max(i1, i2)
            for p in st["rows"]:
                for ch in p.children:
                    ch.selected = False
            for i in range(lo, hi + 1):
                order[i].selected = True
    else:
        for p in st["rows"]:
            for ch in p.children:
                ch.selected = False
        c.selected = True
        st["_anchor"] = c
    for ch in st["_vis_children"]:
        update_row_visual(ch)
    for p in st["rows"]:
        sync_parent_cb(p)
    update_sel_count()


def wire_row_click(tb, c):
    def tbclick(sender, e, c=c):
        cf, sf = mods()
        row_click(c, cf, sf)
    tb.MouseLeftButtonDown += tbclick


def paint_swatch(bcol, c):
    if c.rgb:
        bcol.Background = SolidColorBrush(MColor.FromRgb(c.rgb[0], c.rgb[1], c.rgb[2]))
        bcol.Content = ""
    else:
        bcol.Background = SolidColorBrush(WColors.LightGray)
        bcol.Content = DEF


def update_row_editors(c):
    ui = st["_row_ui"].get(id(c))
    if not ui:
        return
    st["_editing"] = True
    try:
        cbw = ui.get("cbw")
        if cbw is not None:
            cbw.SelectedIndex = c.weight if c.weight else 0
        cbp2 = ui.get("cbp2")
        if cbp2 is not None:
            idx = 0
            if c.pattern_id is not None:
                nm = st["pattern_map"].get(c.pattern_id)
                if nm in st["pattern_order"]:
                    idx = st["pattern_order"].index(nm) + 1
            cbp2.SelectedIndex = idx
        bcol = ui.get("bcol")
        if bcol is not None:
            paint_swatch(bcol, c)
    finally:
        st["_editing"] = False


def selected_targets(c):
    targets = [c]
    if c.selected:
        for p in st["rows"]:
            for ch in p.children:
                if ch is not c and ch.selected:
                    targets.append(ch)
    return targets


def apply_batch_edit(c, prop, value):
    if prop == "pattern":
        prop = "pattern_id"  # legacy-safe normalization (Row attr is pattern_id)
    for t in selected_targets(c):
        setattr(t, prop, value)
        if prop == "pattern_id":
            t.pattern_name = st["pattern_map"].get(value) if value else None
        update_row_editors(t)


def cur_text(c):
    parts = []
    if c.cur_weight is not None:
        parts.append("W{0}".format(c.cur_weight))
    if c.cur_rgb is not None:
        parts.append("R{0}G{1}B{2}".format(c.cur_rgb[0], c.cur_rgb[1], c.cur_rgb[2]))
    if c.cur_pattern_id is not None:
        parts.append(st["pattern_map"].get(c.cur_pattern_id) or "pattern")
    txt = ", ".join(parts) if parts else "default"
    if c.status:
        txt = "{0} [{1}]".format(txt, c.status)
    return txt


def refresh_filter_options(st):
    cbf = st["filter_cb"]
    types = []
    for pr in st["rows"]:
        for c in pr.children:
            if c.view_type not in types:
                types.append(c.view_type)
    types.sort()
    keep = st["type_filter"]
    cbf.Items.Clear()
    cbf.Items.Add("All")
    for t in types:
        cbf.Items.Add(t)
    if keep in types:
        cbf.SelectedItem = keep
    else:
        st["type_filter"] = "All"
        cbf.SelectedIndex = 0


def expand_all():
    for pr in st["rows"]:
        pr.expanded = True
    render(st)


def collapse_all():
    for pr in st["rows"]:
        pr.expanded = False
    render(st)


def render(st):
    st["_row_ui"] = {}
    st["_vis_children"] = []
    st["_anchor"] = None
    st["_editing"] = True
    try:
        tg = st["table_grid"]
        tg.Children.Clear()
        tg.RowDefinitions.Clear()
        tg.ColumnDefinitions.Clear()
        for w in COL_W:
            cd = ColumnDefinition(); cd.Width = GridLength(float(w))
            tg.ColumnDefinitions.Add(cd)
        hdr = RowDefinition(); hdr.Height = GridLength(30)
        tg.RowDefinitions.Add(hdr)
        for i, name in enumerate(HEADERS):
            if not name:
                continue
            tb = TextBlock(); tb.Text = name; tb.FontWeight = FontWeights.Bold
            tb.Margin = Thickness(4, 4, 2, 4)
            tb.VerticalAlignment = VerticalAlignment.Center
            Grid.SetRow(tb, 0); Grid.SetColumn(tb, i)
            tg.Children.Add(tb)
        r = 1
        tf = st["type_filter"]; so = st["show_selected_only"]
        for pr in st["rows"]:
            kids = [c for c in pr.children if (tf == "All" or c.view_type == tf)]
            if not kids:
                continue
            if so and not any(c.selected for c in kids):
                continue
            tg.RowDefinitions.Add(RowDefinition())
            tg.RowDefinitions[r].Height = GridLength(30)
            cbp = CheckBox(); cbp.IsThreeState = True
            cbp.Width = 22; cbp.Height = 22; cbp.Focusable = False
            cbp.HorizontalAlignment = HorizontalAlignment.Left
            cbp.VerticalAlignment = VerticalAlignment.Center
            cbp.Margin = Thickness(6, 0, 0, 0)
            cbp.IsChecked = parent_state_for(pr)
            def pclick(sender, e, pr=pr, cbp=cbp):
                if st.get("_editing"):
                    return
                target = not all(ch.selected for ch in pr.children)
                for ch in pr.children:
                    ch.selected = target
                cbp.IsChecked = True if target else False
                for ch in st["_vis_children"]:
                    update_row_visual(ch)
                for p2 in st["rows"]:
                    if p2 is not pr:
                        sync_parent_cb(p2)
                update_sel_count()
            cbp.Click += pclick
            Grid.SetRow(cbp, r); Grid.SetColumn(cbp, 1)
            tg.Children.Add(cbp)
            st["_row_ui"][id(pr)] = {"parent_cb": cbp}
            bd = Border(); bd.Background = GRAY_BG
            bd.Padding = Thickness(6, 3, 4, 3)
            bd.CornerRadius = CornerRadius(2); bd.Cursor = Cursors.Hand
            sp = StackPanel(); sp.Orientation = Orientation.Horizontal
            arrow = TextBlock()
            arrow.Text = ARROW_EXP if pr.expanded else ARROW_COL
            arrow.FontFamily = FontFamily("Segoe UI Symbol")
            sp.Children.Add(arrow)
            lbl = TextBlock()
            lbl.Text = "  {0} - {1}  ({2} Viewports)".format(
                pr.sheet_num, pr.sheet_name.upper(), len(pr.children))
            lbl.FontWeight = FontWeights.Bold
            sp.Children.Add(lbl)
            bd.Child = sp
            def toggle_exp(sender, e, pr=pr):
                cf, sf = mods()
                if cf or sf:
                    return
                pr.expanded = not pr.expanded
                render(st)
            bd.MouseLeftButtonUp += toggle_exp
            Grid.SetRow(bd, r); Grid.SetColumn(bd, 2); Grid.SetColumnSpan(bd, 5)
            tg.Children.Add(bd)
            cur_txt = TextBlock()
            n_ovr = len([ch for ch in pr.children
                         if ch.cur_weight or ch.cur_rgb or ch.cur_pattern_id])
            cur_txt.Text = "{0} overridden".format(n_ovr)
            cur_txt.Margin = Thickness(4, 4, 2, 4)
            cur_txt.VerticalAlignment = VerticalAlignment.Center
            Grid.SetRow(cur_txt, r); Grid.SetColumn(cur_txt, 10)
            tg.Children.Add(cur_txt)
            r += 1
            if not pr.expanded:
                continue
            for c in kids:
                tg.RowDefinitions.Add(RowDefinition())
                tg.RowDefinitions[r].Height = GridLength(34)
                ov = Border(); ov.Background = TRANS; ov.Cursor = Cursors.Hand
                def ov_click(sender, e, c=c, ov=ov):
                    src = e.OriginalSource
                    while src is not None:
                        if src is ov:
                            break
                        if isinstance(src, (CheckBox, ComboBox, Button)):
                            return
                        src = VisualTreeHelper.GetParent(src)
                    cf, sf = mods()
                    row_click(c, cf, sf)
                ov.PreviewMouseLeftButtonDown += ov_click
                Grid.SetRow(ov, r); Grid.SetColumn(ov, 0)
                Grid.SetColumnSpan(ov, len(COL_W))
                tg.Children.Add(ov)
                cbb = CheckBox(); cbb.IsChecked = bool(c.selected)
                cbb.Width = 24; cbb.Height = 24; cbb.Focusable = False
                cbb.HorizontalAlignment = HorizontalAlignment.Left
                cbb.VerticalAlignment = VerticalAlignment.Center
                cbb.Margin = Thickness(28, 0, 0, 0)
                def cclick(sender, e, c=c, cbb=cbb):
                    if st.get("_editing"):
                        return
                    c.selected = bool(cbb.IsChecked)
                    update_row_visual(c)
                    sync_parent_cb(c.parent)
                    update_sel_count()
                cbb.Click += cclick
                Grid.SetRow(cbb, r); Grid.SetColumn(cbb, 1)
                tg.Children.Add(cbb)
                st["_row_ui"][id(c)] = {"border": ov, "cb": cbb}
                st["_vis_children"].append(c)
                update_row_visual(c)
                def mk(col, text, r=r, c=c):
                    tb = TextBlock(); tb.Text = str(text)
                    tb.Margin = Thickness(4, 0, 2, 0)
                    tb.Padding = Thickness(8, 0, 0, 0)
                    tb.VerticalAlignment = VerticalAlignment.Center
                    tb.Background = TRANS
                    wire_row_click(tb, c)
                    Grid.SetRow(tb, r); Grid.SetColumn(tb, col)
                    tg.Children.Add(tb)
                mk(4, c.view_type)
                mk(5, c.view_name)
                mk(6, c.title_on_sheet or "-")
                cbw = ComboBox(); cbw.Width = 82; cbw.Height = 24
                cbw.VerticalAlignment = VerticalAlignment.Center
                cbw.Items.Add(DEF)
                for i in range(1, 17):
                    cbw.Items.Add(str(i))
                cbw.SelectedIndex = c.weight if c.weight else 0
                def wsel(sender, e, c=c, cbw=cbw):
                    if st.get("_editing"):
                        return
                    v = cbw.SelectedItem
                    val = None if (v is None or v == DEF) else int(v)
                    apply_batch_edit(c, "weight", val)
                cbw.SelectionChanged += wsel
                Grid.SetRow(cbw, r); Grid.SetColumn(cbw, 7)
                tg.Children.Add(cbw)
                bcol = Button(); bcol.Width = 82; bcol.Height = 24
                bcol.VerticalAlignment = VerticalAlignment.Center
                paint_swatch(bcol, c)
                def on_color_pick(sender, e, c=c):
                    dlg = ColorDialog()
                    if c.rgb:
                        dlg.Color = DColor.FromArgb(255, c.rgb[0], c.rgb[1], c.rgb[2])
                    if dlg.ShowDialog() == DialogResult.OK:
                        apply_batch_edit(c, "rgb",
                                         (dlg.Color.R, dlg.Color.G, dlg.Color.B))
                def on_color_clear(sender, e, c=c):
                    apply_batch_edit(c, "rgb", None)
                bcol.Click += on_color_pick
                bcol.MouseRightButtonUp += on_color_clear
                bcol.ToolTip = ("Left-click: pick color. Right-click: clear. "
                                "Edits propagate to all selected rows.")
                Grid.SetRow(bcol, r); Grid.SetColumn(bcol, 8)
                tg.Children.Add(bcol)
                cbp2 = ComboBox(); cbp2.Width = 150; cbp2.Height = 24
                cbp2.VerticalAlignment = VerticalAlignment.Center
                cbp2.Items.Add(DEF)
                for nm in st["pattern_order"]:
                    cbp2.Items.Add(nm)
                idx = 0
                if c.pattern_id is not None:
                    nm = st["pattern_map"].get(c.pattern_id)
                    if nm in st["pattern_order"]:
                        idx = st["pattern_order"].index(nm) + 1
                cbp2.SelectedIndex = idx
                def psel(sender, e, c=c, cbp2=cbp2):
                    if st.get("_editing"):
                        return
                    nm = cbp2.SelectedItem
                    if nm is None or nm == DEF:
                        apply_batch_edit(c, "pattern_id", None)
                    else:
                        apply_batch_edit(c, "pattern_id",
                                         st["pattern_rev"][nm])
                cbp2.SelectionChanged += psel
                Grid.SetRow(cbp2, r); Grid.SetColumn(cbp2, 9)
                tg.Children.Add(cbp2)
                st["_row_ui"][id(c)]["cbw"] = cbw
                st["_row_ui"][id(c)]["cbp2"] = cbp2
                st["_row_ui"][id(c)]["bcol"] = bcol
                cur2 = TextBlock(); cur2.Text = cur_text(c)
                cur2.Margin = Thickness(4, 0, 2, 0)
                cur2.VerticalAlignment = VerticalAlignment.Center
                cur2.Background = TRANS
                wire_row_click(cur2, c)
                Grid.SetRow(cur2, r); Grid.SetColumn(cur2, 10)
                tg.Children.Add(cur2)
                r += 1
    finally:
        st["_editing"] = False
    update_sel_count()


def set_buttons(enabled):
    for key in ("b_sel", "b_all", "b_exp", "b_col", "b_apply", "b_reset"):
        b = st.get(key)
        if b is not None:
            b.IsEnabled = enabled


def raise_mode(mode):
    if st["busy"]:
        return
    st["mode"] = mode
    st["busy"] = True
    set_buttons(False)
    st["status_tb"].Text = "Working..."
    st["event"].Raise()


def after_event():
    st["busy"] = False
    set_buttons(True)
    if st["error"]:
        st["status_tb"].Text = "ERROR: " + st["error"]
        MessageBox.Show(st["win"], "Operation failed:\n" + st["error"])
    else:
        st["status_tb"].Text = st["status"]
    refresh_filter_options(st)
    render(st)


try:
    for _w in list(Application.Current.Windows):
        try:
            if _w.Title and _w.Title.startswith("JMS Tools"):
                _w.Close()
        except Exception:
            pass

    collect_rows(doc, uidoc, "all", st)
    _handler = ViewportCropManagerHandler(st)
    _ev = ExternalEvent.Create(_handler)
    st["handler"] = _handler
    st["event"] = _ev
    st["callback"] = after_event
    st["fns"] = {
        "collect_rows": collect_rows, "apply_overrides": apply_overrides,
        "resolve_crop": resolve_crop, "read_current": read_current,
        "render": render, "refresh_filter_options": refresh_filter_options,
        "row_click": row_click, "apply_batch_edit": apply_batch_edit,
        "update_row_editors": update_row_editors,
        "update_row_visual": update_row_visual,
        "sync_parent_cb": sync_parent_cb, "update_sel_count": update_sel_count,
        "parent_state_for": parent_state_for, "expand_all": expand_all,
        "collapse_all": collapse_all, "selected_targets": selected_targets,
        "paint_swatch": paint_swatch, "cur_text": cur_text,
    }

    _win = Window()
    _win.Title = WIN_TITLE
    _win.Width = 1340; _win.Height = 840
    _win.ResizeMode = ResizeMode.CanResize
    _root = Grid()
    _rd0 = RowDefinition(); _rd0.Height = GridLength.Auto
    _rd1 = RowDefinition(); _rd1.Height = GridLength(1, GridUnitType.Star)
    _rd2 = RowDefinition(); _rd2.Height = GridLength.Auto
    _root.RowDefinitions.Add(_rd0)
    _root.RowDefinitions.Add(_rd1)
    _root.RowDefinitions.Add(_rd2)

    def _mk_btn(text, cb, width=170):
        b = Button(); b.Content = text; b.Width = width; b.Height = 28
        b.Margin = Thickness(0, 0, 8, 0)
        b.Click += cb
        return b

    _bar = StackPanel()
    _row1 = StackPanel(); _row1.Orientation = Orientation.Horizontal
    _row1.Margin = Thickness(8, 8, 8, 2)
    _row2 = StackPanel(); _row2.Orientation = Orientation.Horizontal
    _row2.Margin = Thickness(8, 2, 8, 8)
    _b_sel = _mk_btn("Load From Selection",
                     lambda s, e: raise_mode("load_selection"), 180)
    _b_all = _mk_btn("Load All Sheets", lambda s, e: raise_mode("load_all"), 150)
    _b_exp = _mk_btn("Expand All", lambda s, e: expand_all(), 110)
    _b_col = _mk_btn("Collapse All", lambda s, e: collapse_all(), 115)
    _row1.Children.Add(_b_sel); _row1.Children.Add(_b_all)
    _row1.Children.Add(_b_exp); _row1.Children.Add(_b_col)
    _lbl_f = TextBlock(); _lbl_f.Text = "View Type:"
    _lbl_f.VerticalAlignment = VerticalAlignment.Center
    _lbl_f.Margin = Thickness(0, 0, 6, 0)
    _cbf = ComboBox(); _cbf.Width = 180; _cbf.Height = 28
    _cbf.Margin = Thickness(0, 0, 16, 0)
    def _on_filter(sender, e):
        if st.get("_editing"):
            return
        st["type_filter"] = str(_cbf.SelectedItem) if _cbf.SelectedItem else "All"
        render(st)
    _cbf.SelectionChanged += _on_filter
    _cbs = CheckBox(); _cbs.Content = "Show Selected Only"
    _cbs.VerticalAlignment = VerticalAlignment.Center
    _cbs.Margin = Thickness(0, 0, 16, 0)
    def _on_show_sel(sender, e):
        st["show_selected_only"] = bool(_cbs.IsChecked)
        render(st)
    _cbs.Click += _on_show_sel
    _cbe = CheckBox(); _cbe.Content = "Ensure Crop Visible on Apply"
    _cbe.IsChecked = bool(st["ensure_visible"])
    _cbe.VerticalAlignment = VerticalAlignment.Center
    def _on_ensure(sender, e):
        st["ensure_visible"] = bool(_cbe.IsChecked)
    _cbe.Click += _on_ensure
    _row2.Children.Add(_lbl_f); _row2.Children.Add(_cbf)
    _row2.Children.Add(_cbs); _row2.Children.Add(_cbe)
    _bar.Children.Add(_row1); _bar.Children.Add(_row2)
    Grid.SetRow(_bar, 0)
    _root.Children.Add(_bar)

    _sv = ScrollViewer()
    _sv.HorizontalScrollBarVisibility = ScrollBarVisibility.Auto
    _sv.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    _tg = Grid()
    _sv.Content = _tg
    Grid.SetRow(_sv, 1)
    _root.Children.Add(_sv)

    _bottom = StackPanel(); _bottom.Orientation = Orientation.Horizontal
    _bottom.Margin = Thickness(8)
    _b_apply = _mk_btn("Apply Overrides to Selected",
                       lambda s, e: raise_mode("apply"), 220)
    _b_reset = _mk_btn("Reset Selected to Default",
                       lambda s, e: raise_mode("reset"), 200)
    _tb_status = TextBlock(); _tb_status.Text = st["status"]
    _tb_status.VerticalAlignment = VerticalAlignment.Center
    _tb_status.Margin = Thickness(10, 0, 0, 0)
    _sel_tb = TextBlock(); _sel_tb.VerticalAlignment = VerticalAlignment.Center
    _sel_tb.Margin = Thickness(14, 0, 0, 0)
    _bottom.Children.Add(_b_apply); _bottom.Children.Add(_b_reset)
    _bottom.Children.Add(_tb_status); _bottom.Children.Add(_sel_tb)
    Grid.SetRow(_bottom, 2)
    _root.Children.Add(_bottom)

    st["table_grid"] = _tg; st["filter_cb"] = _cbf
    st["status_tb"] = _tb_status; st["sel_tb"] = _sel_tb
    st["b_sel"] = _b_sel; st["b_all"] = _b_all
    st["b_exp"] = _b_exp; st["b_col"] = _b_col
    st["b_apply"] = _b_apply; st["b_reset"] = _b_reset
    _win.Content = _root
    _win.Tag = st
    st["win"] = _win
    Application.Current.Properties["VIEWPORT_CROP_MANAGER_STATE"] = st
    refresh_filter_options(st)
    render(st)
    _win.Show()
    print("ViewportCropManager launched | sheets: {0} | viewports: {1}".format(
        len(st["rows"]), len([c for pr in st["rows"] for c in pr.children])))
except Exception:
    traceback.print_exc()
    print("ViewportCropManager FAILED to launch")
