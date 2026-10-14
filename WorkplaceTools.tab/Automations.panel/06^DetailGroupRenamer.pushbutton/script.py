# PolyForm Internal Use 1.0.0 - Copyright (C) 2026 Javier Sols
# Source available for inspection and authorized internal use only.

"""
DetailGroupRenamer
Revit 2025 Compatible | .NET 8 | Persistent Engine
v1.3 - Fixed Synchronized Multiselect Checkbox Toggling
"""
# --- 1. PERSISTENCE FLAG ---
__persistentengine__ = True
__title__ = "Detail Group\nRenamer"
__doc__ = "Modeless window to batch rename and clean up Detail Groups model-wide."

# --- 2. CORE IMPORTS & REFERENCES ---
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

# --- 3. DATA MODEL ---
class GroupTypeRow(object):
    def __init__(self, group_type):
        self.group_type_ptr = group_type
        p_name = group_type.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        self.old_name = p_name.AsString() if p_name else ""
        self.suggestion = "" 
        self.final_name = ""
        self.is_valid = True
        self.is_checked = False 

    def refresh_from_element(self):
        """Pulls the actual current name from the Revit Element database."""
        if self.group_type_ptr.IsValidObject:
            p_name = self.group_type_ptr.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
            self.old_name = p_name.AsString() if p_name else ""

# --- 4. THE EXTERNAL EVENT BRIDGE ---
class RenamerHandler(UI.IExternalEventHandler):
    def __init__(self, window):
        self.rows = []
        self.window = window  

    def Execute(self, app):
        if not self.rows: 
            return
        doc = revit.doc
        
        with DB.TransactionGroup(doc, "Batch Rename Detail Groups") as tg:
            tg.Start()
            for row in self.rows:
                if row.is_checked and row.is_valid and row.suggestion and row.group_type_ptr.IsValidObject:
                    if row.old_name == row.suggestion:
                        row.final_name = row.old_name
                        continue
                    try:
                        with DB.Transaction(doc, "Rename Group Type") as t:
                            t.Start()
                            row.group_type_ptr.Name = row.suggestion
                            t.Commit()
                            
                            row.refresh_from_element()
                            row.final_name = row.suggestion
                            row.suggestion = "" 
                            row.is_checked = False 
                    except Exception:
                        row.final_name = "Error / Collision"
            tg.Assimilate()
            
        self.window.process_naming_logic()

    def GetName(self): 
        return "DetailGroupRenamerHandler"

# --- 5. THE UI CONTROLLER ---
class ModelessRenamerWindow(object):
    def __init__(self):
        xaml_str = """
        <Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
                Title="Detail Group Renamer" Height="650" Width="1050" Topmost="True" WindowStartupLocation="CenterScreen">
            <Window.Resources>
                <Style TargetType="DataGridCell">
                    <Style.Triggers>
                        <Trigger Property="IsSelected" Value="True">
                            <Setter Property="Background" Value="#CCE8FF" />
                            <Setter Property="Foreground" Value="Black" />
                        </Trigger>
                    </Style.Triggers>
                </Style>
            </Window.Resources>
            <Grid Margin="15">
                <Grid.RowDefinitions>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="*"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                </Grid.RowDefinitions>
                
                <Grid Grid.Row="0" Margin="0,0,0,10">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="Auto"/>
                        <ColumnDefinition Width="250"/>
                        <ColumnDefinition Width="*"/>
                    </Grid.ColumnDefinitions>
                    <TextBlock Grid.Column="0" Text="Filter List by Name:" VerticalAlignment="Center" FontWeight="SemiBold" Margin="0,0,10,0"/>
                    <TextBox Name="FilterTxt" Grid.Column="1" Height="26" VerticalContentAlignment="Center"/>
                </Grid>
                
                <DataGrid Name="MainGrid" Grid.Row="1" AutoGenerateColumns="False" CanUserAddRows="False" SelectionMode="Extended" AlternatingRowBackground="#F9F9F9">
                    <DataGrid.Columns>
                        <DataGridCheckBoxColumn Header="Rename" Binding="{Binding is_checked}" Width="70" IsReadOnly="True">
                            <DataGridCheckBoxColumn.ElementStyle>
                                <Style TargetType="CheckBox">
                                    <Setter Property="HorizontalAlignment" Value="Center"/>
                                    <Setter Property="VerticalAlignment" Value="Center"/>
                                </Style>
                            </DataGridCheckBoxColumn.ElementStyle>
                        </DataGridCheckBoxColumn>
                        
                        <DataGridTextColumn Header="Current Detail Group Name" Binding="{Binding old_name}" Width="2*" IsReadOnly="True"/>
                        <DataGridTextColumn Header="Modification Preview" Binding="{Binding suggestion}" Width="2*" IsReadOnly="True">
                            <DataGridTextColumn.ElementStyle>
                                <Style TargetType="TextBlock">
                                    <Setter Property="FontWeight" Value="Bold"/>
                                    <Style.Triggers>
                                        <DataTrigger Binding="{Binding is_valid}" Value="False">
                                            <Setter Property="Foreground" Value="#D32F2F"/>
                                        </DataTrigger>
                                        <DataTrigger Binding="{Binding is_valid}" Value="True">
                                            <Setter Property="Foreground" Value="#1565C0"/>
                                        </DataTrigger>
                                    </Style.Triggers>
                                </Style>
                            </DataGridTextColumn.ElementStyle>
                        </DataGridTextColumn>
                        <DataGridTextColumn Header="Execution Status" Binding="{Binding final_name}" Width="1.5*" IsReadOnly="True">
                            <DataGridTextColumn.ElementStyle>
                                <Style TargetType="TextBlock"><Setter Property="Foreground" Value="#2E7D32"/></Style>
                            </DataGridTextColumn.ElementStyle>
                        </DataGridTextColumn>
                    </DataGrid.Columns>
                </DataGrid>
                
                <GroupBox Grid.Row="2" Header="Renaming Rule Setup" Margin="0,15,0,10" Padding="10">
                    <Grid>
                        <Grid.RowDefinitions>
                            <RowDefinition Height="Auto"/>
                            <RowDefinition Height="Auto"/>
                        </Grid.RowDefinitions>
                        <Grid.ColumnDefinitions>
                            <ColumnDefinition Width="Auto"/>
                            <ColumnDefinition Width="*"/>
                            <ColumnDefinition Width="30"/>
                            <ColumnDefinition Width="Auto"/>
                            <ColumnDefinition Width="*"/>
                        </Grid.ColumnDefinitions>
                        
                        <TextBlock Grid.Row="0" Grid.Column="0" Text="Find Text:" VerticalAlignment="Center" Margin="0,0,10,8" HorizontalAlignment="Right"/>
                        <TextBox Name="FindTxt" Grid.Row="0" Grid.Column="1" Height="26" VerticalContentAlignment="Center" Margin="0,0,0,8"/>
                        
                        <TextBlock Grid.Row="1" Grid.Column="0" Text="Replace With:" VerticalAlignment="Center" Margin="0,0,10,0" HorizontalAlignment="Right"/>
                        <TextBox Name="ReplaceTxt" Grid.Row="1" Grid.Column="1" Height="26" VerticalContentAlignment="Center"/>
                        
                        <TextBlock Grid.Row="0" Grid.Column="3" Text="Prefix:" VerticalAlignment="Center" Margin="0,0,10,8" HorizontalAlignment="Right"/>
                        <TextBox Name="PrefixTxt" Grid.Row="0" Grid.Column="4" Height="26" VerticalContentAlignment="Center" Margin="0,0,0,8"/>
                        
                        <TextBlock Grid.Row="1" Grid.Column="3" Text="Suffix:" VerticalAlignment="Center" Margin="0,0,10,0" HorizontalAlignment="Right"/>
                        <TextBox Name="SuffixTxt" Grid.Row="1" Grid.Column="4" Height="26" VerticalContentAlignment="Center"/>
                    </Grid>
                </GroupBox>
                
                <Grid Grid.Row="3">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="*"/>
                        <ColumnDefinition Width="2*"/>
                    </Grid.ColumnDefinitions>
                    <Button Name="RefreshBtn" Grid.Column="0" Content="Reload Model Groups" Height="40" Margin="0,0,5,0" Background="#EEEEEE"/>
                    <Button Name="ApplyBtn" Grid.Column="1" Content="Apply Changes to Selected Rows" Height="40" Background="#1976D2" Foreground="White" FontWeight="Bold"/>
                </Grid>
            </Grid>
        </Window>
        """
        self.ui = XamlReader.Load(XmlReader.Create(StringReader(xaml_str)))
        
        self.grid = self.ui.FindName("MainGrid")
        self.filter_txt = self.ui.FindName("FilterTxt")
        self.find_txt = self.ui.FindName("FindTxt")
        self.replace_txt = self.ui.FindName("ReplaceTxt")
        self.prefix_txt = self.ui.FindName("PrefixTxt")
        self.suffix_txt = self.ui.FindName("SuffixTxt")
        self.refresh_btn = self.ui.FindName("RefreshBtn")
        self.apply_btn = self.ui.FindName("ApplyBtn")
        
        self.handler = RenamerHandler(self)
        self.event = UI.ExternalEvent.Create(self.handler)
        
        self.refresh_btn.Click += self.on_refresh
        self.apply_btn.Click += self.on_apply
        
        self.filter_txt.TextChanged += self.on_filter_changed
        self.find_txt.TextChanged += self.on_rules_changed
        self.replace_txt.TextChanged += self.on_rules_changed
        self.prefix_txt.TextChanged += self.on_rules_changed
        self.suffix_txt.TextChanged += self.on_rules_changed
        
        # Switched to a robust Preview Mouse Down Interceptor to simulate DiRoots
        self.grid.PreviewMouseLeftButtonDown += self.on_grid_preview_mouse_down
        
        self.all_rows = []
        self.load_data()
        
        try:
            handle = System.Diagnostics.Process.GetCurrentProcess().MainWindowHandle
            WindowInteropHelper(self.ui).Owner = handle
        except Exception:
            pass

    def refresh_grid_visuals(self):
        self.grid.Items.Refresh()

    def load_data(self):
        doc = revit.doc
        if not doc: 
            return
            
        raw_types = DB.FilteredElementCollector(doc).OfClass(DB.GroupType).ToElements()
        
        rows_collected = []
        for gt in raw_types:
            if gt.Category and gt.Category.Id.IntegerValue == int(DB.BuiltInParameter.ELEM_TYPE_PARAM):
                continue
            
            if gt.Category and "Detail Groups" in gt.Category.Name:
                rows_collected.append(GroupTypeRow(gt))
                
        self.all_rows = rows_collected
        self.process_naming_logic()

    def on_grid_preview_mouse_down(self, sender, e):
        """Intercepts click events early to sync toggles across highlighted rows instantly."""
        dep = e.OriginalSource
        
        # Traverse up the visual element tree to check if we clicked inside a DataGridCell
        while dep is not None and not isinstance(dep, System.Windows.Controls.DataGridCell):
            dep = System.Windows.Media.VisualTreeHelper.GetParent(dep)
            
        if dep is not None:
            # Check if the clicked cell belongs to the 'Rename' checkbox column
            if dep.Column.Header == "Rename":
                clicked_row_data = dep.DataContext
                
                if hasattr(clicked_row_data, "is_checked"):
                    # Calculate target toggled state based on the item clicked
                    target_state = not clicked_row_data.is_checked
                    
                    selected_items = self.grid.SelectedItems
                    # If multiple rows are highlighted and the clicked row is part of that selection group
                    if selected_items.Count > 1 and clicked_row_data in selected_items:
                        for item in selected_items:
                            if hasattr(item, "is_checked"):
                                item.is_checked = target_state
                    else:
                        # Otherwise, fall back to toggling just the single clicked item row
                        clicked_row_data.is_checked = target_state
                    
                    # Mark event handled to stop WPF from executing conflicting default checkbox cycles
                    e.Handled = True
                    
                    # Recalculate preview strings and update the layout view instantly
                    self.process_naming_logic()

    def process_naming_logic(self):
        find_str = self.find_txt.Text
        replace_str = self.replace_txt.Text
        prefix_str = self.prefix_txt.Text
        suffix_str = self.suffix_txt.Text
        
        predicted_names_pool = set()
        
        for row in self.all_rows:
            if not row.is_checked:
                row.suggestion = "" 
                row.is_valid = True
                continue
                
            base_name = row.old_name
            
            if find_str:
                base_name = base_name.replace(find_str, replace_str)
                
            calculated_name = "{}{}{}".format(prefix_str, base_name, suffix_str)
            row.suggestion = calculated_name
            row.is_valid = True  
            
            if not calculated_name.strip() or any(char in calculated_name for char in ['\\', ':', '{', '}', '[', ']', '|', ';', '<', '>', '?', '`', '~']):
                row.is_valid = False
                row.suggestion = "Error: Invalid Name String"

        for row in self.all_rows:
            if not row.is_checked or not row.is_valid: 
                continue
            if row.suggestion in predicted_names_pool and row.suggestion != row.old_name:
                row.is_valid = False
                row.suggestion = "Collision: Duplicate Name Detected"
            else:
                predicted_names_pool.add(row.suggestion)
                
        self.apply_live_filter()

    def apply_live_filter(self):
        search_query = self.filter_txt.Text.lower().strip()
        
        if not search_query:
            self.grid.ItemsSource = self.all_rows
        else:
            filtered_list = [row for row in self.all_rows if search_query in row.old_name.lower()]
            self.grid.ItemsSource = filtered_list
            
        self.refresh_grid_visuals()

    def on_filter_changed(self, sender, e):
        self.apply_live_filter()

    def on_rules_changed(self, sender, e):
        self.process_naming_logic()

    def on_refresh(self, sender, e):
        self.load_data()

    def on_apply(self, sender, e):
        checked_items = [row for row in self.all_rows if row.is_checked]
        if not checked_items:
            forms.alert("Please check the 'Rename' column for rows you want to rename first.")
            return
            
        self.handler.rows = checked_items
        self.event.Raise()

    def show(self):
        self.ui.Show()

# --- ENTRY INITIALIZATION EXTENSION ---
if __name__ == "__main__":
    window_instance = ModelessRenamerWindow()
    window_instance.show()
