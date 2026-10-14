# PolyForm Internal Use 1.0.0 - Copyright (C) 2026 Javier Sols
# Source available for inspection and authorized internal use only.

"""
ViewSourcetoSubCat v7.1
Revit 2025 Compatible | .NET 8
Bug Fix: Restored missing .show() method and added safe window ownership.
"""
__persistentengine__ = True 
__title__ = "ViewSource to\nSubCat v7.1"

import clr
import System
import re

clr.AddReference('System')
clr.AddReference('System.Xml')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('RevitAPI') 
clr.AddReference('RevitAPIUI')

from System.IO import StringReader
from System.Xml import XmlReader
from System.Windows.Markup import XamlReader
from System.Windows.Interop import WindowInteropHelper
import Autodesk.Revit.DB as DB
import Autodesk.Revit.UI as UI_API
from pyrevit import revit, forms, UI

# --- DATA MODEL ---
class ViewRow(object):
    def __init__(self, view):
        self.view_ptr = view
        self.old_name = view.Name or ""
        self.view_type = view.ViewType.ToString()
        
        # Scale Mapping
        scale_val = view.Scale
        scale_map = {1: '12" = 1\'-0"', 1.5: '8" = 1\'-0"', 2: '6" = 1\'-0"', 4: '3" = 1\'-0"', 
                     8: '1 1/2" = 1\'-0"', 12: '1" = 1\'-0"', 16: '3/4" = 1\'-0"', 24: '1/2" = 1\'-0"', 
                     32: '3/8" = 1\'-0"', 48: '1/4" = 1\'-0"', 64: '3/16" = 1\'-0"', 96: '1/8" = 1\'-0"'}
        self.view_scale = scale_map.get(scale_val, "1:{}".format(scale_val))

        p_sub = view.LookupParameter("View.SubCategory")
        self.sub_cat = p_sub.AsString() if p_sub and p_sub.HasValue else ""
        
        p_src = view.LookupParameter("Source.Project")
        self.source_project = p_src.AsString() if p_src and p_src.HasValue else ""
        
        self.suggestion = ""
        self.final_name = ""

    def refresh_from_element(self):
        if self.view_ptr.IsValidObject:
            self.old_name = self.view_ptr.Name

# --- EXTERNAL EVENT ---
class RenameHandler(UI.IExternalEventHandler):
    def __init__(self, window):
        self.rows = []
        self.window = window
        
    def Execute(self, app):
        if not self.rows: return
        doc = revit.doc
        
        with DB.TransactionGroup(doc, "Rename Views v7.1") as tg:
            tg.Start()
            for row in self.rows:
                if row.suggestion and "Invalid" not in row.suggestion and row.view_ptr.IsValidObject:
                    try:
                        with DB.Transaction(doc, "Rename") as t:
                            t.Start()
                            row.view_ptr.Name = row.suggestion
                            t.Commit()
                            row.refresh_from_element()
                            row.final_name = row.suggestion
                    except Exception:
                        row.final_name = "Error: Already Exists"
            tg.Assimilate()
        self.window.refresh_grid_visuals()

    def GetName(self): return "SubCatRenameHandlerV71"

# --- THE UI ---
class ModelessRenamer(object):
    def __init__(self):
        xaml_str = """
        <Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
                Title="View Source to SubCat v7.1" Height="600" Width="1150" Topmost="True" WindowStartupLocation="CenterScreen">
            <Grid Margin="15">
                <Grid.RowDefinitions><RowDefinition Height="*"/><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
                <Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="70"/></Grid.ColumnDefinitions>
                
                <DataGrid Name="MainGrid" Grid.Column="0" AutoGenerateColumns="False" CanUserAddRows="False" SelectionMode="Extended" AlternatingRowBackground="#F0F0F0">
                    <DataGrid.Columns>
                        <DataGridTextColumn Header="Current Name" Binding="{Binding old_name}" Width="2*" IsReadOnly="True"/>
                        <DataGridTextColumn Header="SubCategory" Binding="{Binding sub_cat}" Width="1*" IsReadOnly="True"/>
                        <DataGridTextColumn Header="Scale" Binding="{Binding view_scale}" Width="0.8*" IsReadOnly="True"/>
                        <DataGridTextColumn Header="Source.Project" Binding="{Binding source_project}" Width="1*" IsReadOnly="True"/>
                        <DataGridTextColumn Header="Modification Suggestion" Binding="{Binding suggestion}" Width="2*" IsReadOnly="True">
                             <DataGridTextColumn.ElementStyle>
                                <Style TargetType="TextBlock"><Setter Property="FontWeight" Value="Bold"/></Style>
                             </DataGridTextColumn.ElementStyle>
                        </DataGridTextColumn>
                        <DataGridTextColumn Header="Final Name" Binding="{Binding final_name}" Width="2*" IsReadOnly="True">
                            <DataGridTextColumn.ElementStyle>
                                <Style TargetType="TextBlock"><Setter Property="Foreground" Value="#2E7D32"/></Style>
                            </DataGridTextColumn.ElementStyle>
                        </DataGridTextColumn>
                    </DataGrid.Columns>
                </DataGrid>

                <StackPanel Grid.Column="1" VerticalAlignment="Center" Margin="10,0,0,0">
                    <Button Name="UpBtn" Content="MOVE\nUP" Height="60" Margin="0,0,0,10" Background="#EEEEEE"/>
                    <Button Name="DownBtn" Content="MOVE\nDN" Height="60" Background="#EEEEEE"/>
                </StackPanel>

                <Button Name="AnalyzeBtn" Grid.Row="1" Grid.ColumnSpan="2" Content="1. Analyze Order &amp; Generate Names" Height="35" Margin="0,15,0,5" Background="#9C27B0" Foreground="White" FontWeight="Bold"/>
                <Grid Grid.Row="2" Grid.ColumnSpan="2">
                    <Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
                    <Button Name="RefreshBtn" Grid.Column="0" Content="Update Selection" Height="40" Margin="0,0,5,0"/>
                    <Button Name="ApplyBtn" Grid.Column="1" Content="2. Apply Changes to Selected" Height="40" Background="#1976D2" Foreground="White" FontWeight="Bold"/>
                </Grid>
            </Grid>
        </Window>
        """
        self.ui = XamlReader.Load(XmlReader.Create(StringReader(xaml_str)))
        self.grid = self.ui.FindName("MainGrid")
        
        self.handler = RenameHandler(self)
        self.event = UI.ExternalEvent.Create(self.handler)
        
        self.ui.FindName("UpBtn").Click += self.move_up
        self.ui.FindName("DownBtn").Click += self.move_down
        self.ui.FindName("AnalyzeBtn").Click += self.on_analyze
        self.ui.FindName("ApplyBtn").Click += self.on_apply
        self.ui.FindName("RefreshBtn").Click += self.on_refresh
        
        self.load_data()

        # Safe Window Ownership setup for .NET 8 / Revit 2025
        try:
            uiapp = clr.Convert(UI_API.UIApplication, revit.uiapp)
            if hasattr(uiapp, "MainWindowHandle"):
                handle = uiapp.MainWindowHandle
                if handle and handle != System.IntPtr.Zero:
                    WindowInteropHelper(self.ui).Owner = handle
        except:
            pass

    def refresh_grid_visuals(self):
        self.grid.Items.Refresh()

    def load_data(self):
        uidoc = revit.uidoc
        if uidoc:
            ids = uidoc.Selection.GetElementIds()
            rows = []
            for i in ids:
                el = uidoc.Document.GetElement(i)
                if isinstance(el, DB.View) and el.ViewType == DB.ViewType.DraftingView:
                    rows.append(ViewRow(el))
            self.grid.ItemsSource = rows

    def move_up(self, sender, e):
        items = list(self.grid.ItemsSource)
        sel = sorted([i for i in self.grid.SelectedItems], key=lambda x: items.index(x))
        if not sel or items.index(sel[0]) == 0: return
        idx = items.index(sel[0]) - 1
        for i in sel: items.remove(i)
        for i, item in enumerate(sel): items.insert(idx + i, item)
        self.grid.ItemsSource = items
        for i in sel: self.grid.SelectedItems.Add(i)
        self.refresh_grid_visuals()

    def move_down(self, sender, e):
        items = list(self.grid.ItemsSource)
        sel = sorted([i for i in self.grid.SelectedItems], key=lambda x: items.index(x))
        if not sel or items.index(sel[-1]) == len(items) - 1: return
        idx = items.index(sel[0]) + 1
        for i in sel: items.remove(i)
        for i, item in enumerate(sel): items.insert(idx + i, item)
        self.grid.ItemsSource = items
        for i in sel: self.grid.SelectedItems.Add(i)
        self.refresh_grid_visuals()

    def on_refresh(self, sender, e): self.load_data()

    def on_analyze(self, sender, e):
        rows = self.grid.ItemsSource
        if not rows: return
        all_names = [v.Name for v in DB.FilteredElementCollector(revit.doc).OfClass(DB.View)]
        known_exceptions = ["PLAN", "SECT", "ELEV", "AXO"]

        for row in rows:
            if not row.sub_cat:
                row.suggestion = "Invalid: No SubCategory Value"
                continue

            anchor_match = re.search(r'^(.*["\']_)', row.old_name)
            if not anchor_match:
                row.suggestion = "Invalid Naming Structure"
                continue
            
            prefix_scale = anchor_match.group(1) 
            remainder = row.old_name[len(prefix_scale):] 

            view_particle = ""
            project_matched = False
            
            if row.source_project:
                proj_escaped = re.escape(row.source_project)
                proj_match = re.search(proj_escaped, remainder, re.IGNORECASE)
                
                if proj_match:
                    project_matched = True
                    in_between = remainder[:proj_match.start()].strip("_")
                    if in_between:
                        view_particle = in_between 

            if not project_matched:
                for xc in known_exceptions:
                    if remainder.upper().startswith(xc + "_"):
                        view_particle = xc
                        break
                else:
                    if row.source_project and row.source_project.lower() not in row.old_name.lower():
                        row.suggestion = "Invalid: Project Typo Mismatch"
                        continue

            if view_particle:
                base_string = "{}{}_{}_".format(prefix_scale, view_particle, row.sub_cat)
            else:
                base_string = "{}{}_".format(prefix_scale, row.sub_cat)

            num = 1
            while True:
                candidate = "{}{:02d}".format(base_string, num)
                if candidate not in all_names and not any(r.suggestion == candidate for r in rows if r != row):
                    row.suggestion = candidate
                    break
                num += 1
                
        self.refresh_grid_visuals()

    def on_apply(self, sender, e):
        self.handler.rows = [i for i in self.grid.SelectedItems]
        self.event.Raise()

    def show(self):
        """Displays the WPF Window."""
        self.ui.Show()

if __name__ == "__main__":
    win = ModelessRenamer()
    win.show()
