# PolyForm Internal Use 1.0.0 - Copyright (C) 2026 Javier Sols
# Source available for inspection and authorized internal use only.

"""
SyncTitleonSheet
Revit 2025+ Compatible | .NET 8 Framework
Complete Modeless Deployment Script + XAML Layout
"""

# --- 1. PERSISTENCE ENGINE FLAG ---
__persistentengine__ = True
__title__ = "Sync Title\non Sheet"
__doc__ = "Synchronizes selected View Names to their 'Title on Sheet' parameter value. Supports both direct view selection and viewports on sheets."

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
from System.Windows.Interop import WindowInteropHelper
import Autodesk.Revit.DB as DB
import Autodesk.Revit.UI as UI_API
from pyrevit import revit, forms, UI

# --- 2. DATA MODEL ---
class SyncViewRow(object):
    def __init__(self, view):
        self.view_ptr = view
        self.view_name = view.get_Parameter(DB.BuiltInParameter.VIEW_NAME).AsString() or ""
        
        # Pull BuiltInParameter for Title on Sheet
        p_title = view.get_Parameter(DB.BuiltInParameter.VIEW_DESCRIPTION)
        self.current_title = p_title.AsString() if p_title and p_title.HasValue else ""
        
        # Default proposed string matches the View Name
        self._proposed_title = self.view_name
        self.sync_status = "Pending"

    @property
    def proposed_title(self):
        return self._proposed_title

    @proposed_title.setter
    def proposed_title(self, value):
        self._proposed_title = value

    def refresh_from_element(self):
        """Pulls the actual parameter value back from the Revit element after transaction."""
        if self.view_ptr.IsValidObject:
            p_title = self.view_ptr.get_Parameter(DB.BuiltInParameter.VIEW_DESCRIPTION)
            self.current_title = p_title.AsString() if p_title and p_title.HasValue else ""

# --- 3. EXTERNAL EVENT LOGIC ---
class SyncSheetHandler(UI.IExternalEventHandler):
    def __init__(self, window_inst):
        self.rows_to_process = []
        self.ui_window = window_inst

    def Execute(self, app):
        import Autodesk.Revit.DB as DB
        if not self.rows_to_process:
            return

        doc = revit.doc
        # Group changes into a single undo block
        with DB.TransactionGroup(doc, "Sync Title on Sheet Macro") as tg:
            tg.Start()
            
            for row in self.rows_to_process:
                if not row.view_ptr.IsValidObject:
                    row.sync_status = "Failed: Invalid Object"
                    continue
                
                try:
                    p_title = row.view_ptr.get_Parameter(DB.BuiltInParameter.VIEW_DESCRIPTION)
                    if p_title is None:
                        row.sync_status = "Error: Param Missing"
                        continue
                        
                    if p_title.IsReadOnly:
                        row.sync_status = "Locked / Read-Only"
                        continue

                    # Execute atomic modification
                    with DB.Transaction(doc, "Sync Title on Sheet") as t:
                        t.Start()
                        p_title.Set(row.proposed_title)
                        t.Commit()
                    
                    row.refresh_from_element()
                    row.sync_status = "Success"
                    
                except Exception as ex:
                    row.sync_status = "Error"
            
            tg.Assimilate()
        
        # Signal back to the UI thread to redraw the grid visuals
        self.ui_window.refresh_grid_visuals()

    def GetName(self):
        return "SyncTitleonSheetHandler"

# --- 4. THE UI & CONTROLLER ---
class ModelessSyncWindow(object):
    def __init__(self):
        xaml_str = """
        <Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
                Title="Sync Title on Sheet Utility" Height="650" Width="1150" 
                Topmost="True" WindowStartupLocation="CenterScreen" Background="#F5F5F5">
            <Window.Resources>
                <Style TargetType="DataGridCell">
                    <Style.Triggers>
                        <Trigger Property="IsSelected" Value="True">
                            <Setter Property="Background" Value="#D2E5F7" />
                            <Setter Property="Foreground" Value="#000000" />
                        </Trigger>
                    </Style.Triggers>
                </Style>
            </Window.Resources>
            <Grid Margin="15">
                <Grid.RowDefinitions>
                    <RowDefinition Height="*" />
                    <RowDefinition Height="Auto" />
                    <RowDefinition Height="Auto" />
                </Grid.RowDefinitions>
                
                <DataGrid Name="SyncGrid" Grid.Row="0" AutoGenerateColumns="False" 
                          CanUserAddRows="False" SelectionMode="Extended" 
                          AlternatingRowBackground="#FAFAFA" GridLinesVisibility="Horizontal" 
                          HorizontalGridLinesBrush="#E0E0E0">
                    <DataGrid.Columns>
                        <DataGridTextColumn Header="View Name" Binding="{Binding view_name}" Width="2*" IsReadOnly="True"/>
                        <DataGridTextColumn Header="Current Title on Sheet" Binding="{Binding current_title}" Width="2*" IsReadOnly="True"/>
                        
                        <DataGridTextColumn Header="Proposed Title on Sheet (Editable)" Binding="{Binding proposed_title, Mode=TwoWay, UpdateSourceTrigger=PropertyChanged}" Width="2*">
                            <DataGridTextColumn.ElementStyle>
                                <Style TargetType="TextBlock">
                                    <Setter Property="Foreground" Value="#0D47A1"/>
                                    <Setter Property="FontWeight" Value="SemiBold"/>
                                </Style>
                            </DataGridTextColumn.ElementStyle>
                        </DataGridTextColumn>
                        
                        <DataGridTextColumn Header="Sync Status" Binding="{Binding sync_status}" Width="1.5*" IsReadOnly="True">
                            <DataGridTextColumn.ElementStyle>
                                <Style TargetType="TextBlock">
                                    <Style.Triggers>
                                        <Trigger Property="Text" Value="Success">
                                            <Setter Property="Foreground" Value="#2E7D32"/>
                                            <Setter Property="FontWeight" Value="Bold"/>
                                        </Trigger>
                                        <Trigger Property="Text" Value="Pending">
                                            <Setter Property="Foreground" Value="#757575"/>
                                        </Trigger>
                                        <Trigger Property="Text" Value="Locked / Read-Only">
                                            <Setter Property="Foreground" Value="#C62828"/>
                                            <Setter Property="FontWeight" Value="Medium"/>
                                        </Trigger>
                                        <Trigger Property="Text" Value="Error">
                                            <Setter Property="Foreground" Value="#C62828"/>
                                            <Setter Property="FontWeight" Value="Medium"/>
                                        </Trigger>
                                    </Style.Triggers>
                                </Style>
                            </DataGridTextColumn.ElementStyle>
                        </DataGridTextColumn>
                    </DataGrid.Columns>
                </DataGrid>

                <Button Name="RefreshSelectionBtn" Grid.Row="1" Content="Update Selection from Active Selection" Height="35" Margin="0,15,0,5" Background="#E0E0E0" Foreground="#212121" FontWeight="Medium"/>
                
                <Grid Grid.Row="2">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="*" />
                        <ColumnDefinition Width="*" />
                    </Grid.ColumnDefinitions>
                    <Button Name="SyncSelectedBtn" Grid.Column="0" Content="Sync Selected Rows Only" Height="45" Margin="0,5,5,0" Background="#1976D2" Foreground="White" FontWeight="Bold"/>
                    <Button Name="SyncAllBtn" Grid.Column="1" Content="Sync All Rows (Batch)" Height="45" Margin="5,5,0,0" Background="#388E3C" Foreground="White" FontWeight="Bold"/>
                </Grid>
            </Grid>
        </Window>
        """
        self.ui = XamlReader.Load(XmlReader.Create(StringReader(xaml_str)))
        self.grid = self.ui.FindName("SyncGrid")
        
        # Bind Controls
        self.ui.FindName("RefreshSelectionBtn").Click += self.on_refresh_selection
        self.ui.FindName("SyncSelectedBtn").Click += self.on_sync_selected
        self.ui.FindName("SyncAllBtn").Click += self.on_sync_all
        
        # Initialize Modeless Communications Framework
        self.handler = SyncSheetHandler(self)
        self.event_bridge = UI.ExternalEvent.Create(self.handler)
        
        self.load_target_views()
        self.attach_owner_handle()

    def attach_owner_handle(self):
        try:
            handle = System.Diagnostics.Process.GetCurrentProcess().MainWindowHandle
            WindowInteropHelper(self.ui).Owner = handle
        except:
            pass

    def load_target_views(self):
        """Collects, translates, and filters active selection from Revit UI."""
        uidoc = revit.uidoc
        if not uidoc:
            return
            
        selection_ids = uidoc.Selection.GetElementIds()
        doc = uidoc.Document
        row_collection = []
        processed_view_ids = set() 

        for eid in selection_ids:
            element = doc.GetElement(eid)
            if not element:
                continue

            target_view = None

            # Path A: Direct View Selection
            if isinstance(element, DB.View):
                target_view = element

            # Path B: Viewport Selection
            elif isinstance(element, DB.Viewport):
                view_id = element.ViewId
                if view_id and view_id != DB.ElementId.InvalidElementId:
                    target_view = doc.GetElement(view_id)

            # Validation & Clean Filtering Block
            if target_view and isinstance(target_view, DB.View) and not target_view.IsTemplate:
                if target_view.Id in processed_view_ids:
                    continue
                
                if target_view.ViewType in [DB.ViewType.Internal, DB.ViewType.ProjectBrowser, DB.ViewType.DrawingSheet]:
                    continue
                    
                processed_view_ids.add(target_view.Id)
                row_collection.append(SyncViewRow(target_view))
                
        self.grid.ItemsSource = row_collection
        self.refresh_grid_visuals()

    def refresh_grid_visuals(self):
        self.grid.Items.Refresh()

    def on_refresh_selection(self, sender, e):
        self.load_target_views()

    def on_sync_selected(self, sender, e):
        selected_items = [item for item in self.grid.SelectedItems]
        if not selected_items:
            forms.alert("No rows selected in UI grid. Highlight rows to sync.")
            return
            
        self.handler.rows_to_process = selected_items
        self.event_bridge.Raise()

    def on_sync_all(self, sender, e):
        all_items = [item for item in self.grid.ItemsSource]
        if not all_items:
            forms.alert("The grid contains no data rows to synchronize.")
            return
            
        self.handler.rows_to_process = all_items
        self.event_bridge.Raise()

    def show(self):
        self.ui.Show()

# --- 5. INITIALIZATION ENTRY ---
if __name__ == "__main__":
    sync_tool_window = ModelessSyncWindow()
    sync_tool_window.show()
