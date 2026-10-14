# PolyForm Internal Use 1.0.0 - Copyright (C) 2026 Javier Sols
# Source available for inspection and authorized internal use only.

"""
Detail Group Name Sync v3
Revit 2025 Compatible | .NET 8
Synchronizes Detail Group names with their Parent Drafting Views.
"""
__persistentengine__ = True 
__title__ = "Detail Group\nName Sync v3"

import clr
import System

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
import Autodesk.Revit.DB as DB
import Autodesk.Revit.UI as UI_API
from pyrevit import revit, UI

# --- 1. DATA MODEL ---
class GroupRow(object):
    def __init__(self, view):
        self.view_ptr = view
        self.view_name = view.Name
        self.group_type_ptr = None
        self.current_group_name = "No Group Found" 
        self.suggestion = ""
        self.final_name = ""
        self.is_valid = False
        
        # Populate current group name immediately on load
        self._harvest_current_group()

    def _harvest_current_group(self):
        """Internal check to find the group in the view during initialization."""
        doc = self.view_ptr.Document
        col = DB.FilteredElementCollector(doc, self.view_ptr.Id).OfClass(DB.Group).ToElements()
        top_level_groups = [g for g in col if g.GroupId == DB.ElementId.InvalidElementId]
        
        if len(top_level_groups) == 1:
            self.group_type_ptr = top_level_groups[0].GroupType
            self.current_group_name = self.group_type_ptr.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
        elif len(top_level_groups) > 1:
            self.current_group_name = "Multiple Groups Found"

    def refresh_names(self):
        if self.group_type_ptr and self.group_type_ptr.IsValidObject:
            self.current_group_name = self.group_type_ptr.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString()

# --- 2. EXTERNAL EVENT ---
class GroupSyncHandler(UI.IExternalEventHandler):
    def __init__(self, window):
        self.rows = []
        self.window = window 
        
    def Execute(self, app):
        if not self.rows: return
        doc = revit.doc
        
        with DB.TransactionGroup(doc, "Sync Detail Group Names") as tg:
            tg.Start()
            for row in self.rows:
                if row.is_valid and row.suggestion.startswith("DG_"):
                    try:
                        with DB.Transaction(doc, "Sync Group Type Name") as t:
                            t.Start()
                            row.group_type_ptr.Name = row.suggestion
                            t.Commit()
                            # Update UI row data with the actual new name
                            row.refresh_names()
                            row.final_name = row.current_group_name 
                    except Exception:
                        row.final_name = "Error"
            tg.Assimilate()
        
        self.window.refresh_grid_visuals()

    def GetName(self): return "GroupSyncHandler"

# --- 3. THE UI ---
class ModelessSyncWindow(object):
    def __init__(self):
        xaml_str = """
        <Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
                Title="Detail Group Name Sync (Tool #2.5)" Height="550" Width="1000" Topmost="True" WindowStartupLocation="CenterScreen">
            <Grid Margin="15">
                <Grid.RowDefinitions>
                    <RowDefinition Height="*"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                </Grid.RowDefinitions>
                
                <DataGrid Name="MainGrid" AutoGenerateColumns="False" CanUserAddRows="False" AlternatingRowBackground="#F9F9F9">
                    <DataGrid.Columns>
                        <DataGridTextColumn Header="Drafting View Name" Binding="{Binding view_name}" Width="1.5*" IsReadOnly="True"/>
                        <DataGridTextColumn Header="Detail Group Name (Original)" Binding="{Binding current_group_name}" Width="1.5*" IsReadOnly="True"/>
                        <DataGridTextColumn Header="Detail Group Name (Suggestion)" Binding="{Binding suggestion}" Width="2*" IsReadOnly="True">
                             <DataGridTextColumn.ElementStyle>
                                <Style TargetType="TextBlock">
                                    <Setter Property="FontWeight" Value="Bold"/>
                                    <Style.Triggers>
                                        <DataTrigger Binding="{Binding is_valid}" Value="False">
                                            <Setter Property="Foreground" Value="Red"/>
                                        </DataTrigger>
                                        <DataTrigger Binding="{Binding is_valid}" Value="True">
                                            <Setter Property="Foreground" Value="#1565C0"/>
                                        </DataTrigger>
                                    </Style.Triggers>
                                </Style>
                            </DataGridTextColumn.ElementStyle>
                        </DataGridTextColumn>
                        <DataGridTextColumn Header="Final Detail Group Name" Binding="{Binding final_name}" Width="1.5*" IsReadOnly="True">
                             <DataGridTextColumn.ElementStyle>
                                <Style TargetType="TextBlock"><Setter Property="Foreground" Value="#2E7D32"/></Style>
                            </DataGridTextColumn.ElementStyle>
                        </DataGridTextColumn>
                    </DataGrid.Columns>
                </DataGrid>

                <Button Name="AnalyzeBtn" Grid.Row="1" Content="Analyze Selected Views" Height="35" Margin="0,15,0,5" Background="#4CAF50" Foreground="White" FontWeight="Bold"/>
                <Grid Grid.Row="2">
                    <Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
                    <Button Name="RefreshBtn" Grid.Column="0" Content="Update View Selection" Height="40" Margin="0,0,5,0"/>
                    <Button Name="ApplyBtn" Grid.Column="1" Content="Apply Syncing" Height="40" Background="#1976D2" Foreground="White" FontWeight="Bold"/>
                </Grid>
            </Grid>
        </Window>
        """
        self.ui = XamlReader.Load(XmlReader.Create(StringReader(xaml_str)))
        self.grid = self.ui.FindName("MainGrid")
        self.handler = GroupSyncHandler(self)
        self.event = UI.ExternalEvent.Create(self.handler)
        
        self.ui.FindName("AnalyzeBtn").Click += self.on_analyze
        self.ui.FindName("ApplyBtn").Click += self.on_apply
        self.ui.FindName("RefreshBtn").Click += self.on_refresh
        
        self.load_data()

    def refresh_grid_visuals(self):
        self.grid.Items.Refresh()

    def load_data(self):
        uidoc = revit.uidoc
        if not uidoc: return
        ids = uidoc.Selection.GetElementIds()
        rows = []
        for i in ids:
            el = uidoc.Document.GetElement(i)
            if isinstance(el, DB.View) and el.ViewType == DB.ViewType.DraftingView:
                rows.append(GroupRow(el))
        self.grid.ItemsSource = rows

    def on_refresh(self, sender, e): self.load_data()

    def on_analyze(self, sender, e):
        rows = self.grid.ItemsSource
        if not rows: return
        doc = revit.doc
        
        existing_type_names = [DB.Element.Name.__get__(gt) for gt in DB.FilteredElementCollector(doc).OfClass(DB.GroupType)]

        for row in rows:
            col = DB.FilteredElementCollector(doc, row.view_ptr.Id).OfClass(DB.Group).ToElements()
            top_level_groups = [g for g in col if g.GroupId == DB.ElementId.InvalidElementId]
            
            if len(top_level_groups) == 0:
                row.suggestion = "Error: Multi/Zero Groups"
                row.is_valid = False
            elif len(top_level_groups) > 1:
                row.suggestion = "Error: Multi/Zero Groups"
                row.is_valid = False
            else:
                target_group = top_level_groups[0]
                row.group_type_ptr = target_group.GroupType
                row.refresh_names()
                
                new_name = "DG_" + row.view_name
                row.suggestion = new_name
                
                if new_name in existing_type_names and row.current_group_name != new_name:
                    row.suggestion = "Naming Conflict"
                    row.is_valid = False
                else:
                    row.is_valid = True
                    
        self.refresh_grid_visuals()

    def on_apply(self, sender, e):
        self.handler.rows = [i for i in self.grid.SelectedItems]
        self.event.Raise()

    def show(self):
        self.ui.Show()

if __name__ == "__main__":
    win = ModelessSyncWindow()
    win.show()
