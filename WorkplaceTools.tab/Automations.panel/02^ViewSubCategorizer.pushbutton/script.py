# PolyForm Internal Use 1.0.0 - Copyright (C) 2026 Javier Sols
# Source available for inspection and authorized internal use only.

"""
ViewSubCategorizer
Revit 2025 Compatible | .NET 8 | Persistent Engine
v6 - Dual Parameter Support (Source & SubCategory)
"""
# --- 1. PERSISTENCE FLAG (CRITICAL) ---
__persistentengine__ = True 
__title__ = "View SubCat\nManager"
__doc__ = "Modeless window for managing View SubCategories and Project Source."

# --- 2. CORE IMPORTS & REFERENCES ---
import clr
import System

# Load Assemblies
clr.AddReference('System.Xml')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('RevitAPI') 
clr.AddReference('RevitAPIUI')

from System.IO import StringReader
from System.Collections.Generic import List
from System.Xml import XmlReader
from System.Windows.Markup import XamlReader
from System.Windows.Interop import WindowInteropHelper

# Import DB directly
import Autodesk.Revit.DB as DB
import Autodesk.Revit.UI as UI_API
from pyrevit import revit, forms, UI

# --- CONFIGURATION CONSTANTS (Global) ---
P_T2_TYPE = "View.Type"
P_T3_SUBCAT = "View.SubCategory"
P_T3_SOURCE = "Source.Project"

# --- HELPER FUNCTIONS ---
def format_imperial_scale(scale_value):
    scale_map = {1: '12" = 1\'-0"', 1.5: '8" = 1\'-0"', 2: '6" = 1\'-0"', 4: '3" = 1\'-0"', 
                 8: '1 1/2" = 1\'-0"', 12: '1" = 1\'-0"', 16: '3/4" = 1\'-0"', 24: '1/2" = 1\'-0"', 
                 32: '3/8" = 1\'-0"', 48: '1/4" = 1\'-0"', 64: '3/16" = 1\'-0"', 96: '1/8" = 1\'-0"', 
                 128: '3/32" = 1\'-0"', 192: '1/16" = 1\'-0"', 384: '1/32" = 1\'-0"'}
    return scale_map.get(scale_value, "1 : {}".format(int(scale_value)) if scale_value else "N/A")

# --- DATA MODEL ---
class ViewRow(object):
    def __init__(self, view):
        # We assume DB is available here (Main Thread execution)
        self.view_ptr = view
        self.name = view.Name or ""
        
        # 1. Type Parameters
        p_type = view.get_Parameter(DB.BuiltInParameter.ELEM_TYPE_PARAM)
        self.t2_ootb = p_type.AsValueString() if p_type else "N/A"
        
        p_t2c = view.LookupParameter(P_T2_TYPE)
        self.t2_custom = p_t2c.AsString() if p_t2c and p_t2c.AsString() else ""
        
        self.view_scale = format_imperial_scale(view.Scale)
        
        # 2. Tier 3 - SubCategory
        p_t3 = view.LookupParameter(P_T3_SUBCAT)
        self.t3 = p_t3.AsString() if p_t3 and p_t3.AsString() else ""

        # 3. Tier 3 - Source Project
        p_src = view.LookupParameter(P_T3_SOURCE)
        self.t3_source = p_src.AsString() if p_src and p_src.AsString() else ""

# --- THE BRIDGE (EXTERNAL EVENT) ---
class SubCatHandler(UI.IExternalEventHandler):
    def __init__(self):
        self.view_rows = []
        self.new_value = ""
        self.target_param = "" # Name of the parameter to update

    def Execute(self, app):
        # 1. Thread Safety Imports
        import Autodesk.Revit.DB as DB
        
        if not self.view_rows or not self.target_param:
            return

        # Defensive check for valid document
        try:
            doc = self.view_rows[0].view_ptr.Document
        except Exception:
            return
        
        try:
            with DB.Transaction(doc, "Update Metadata Modeless") as t:
                t.Start()
                for row in self.view_rows:
                    if row.view_ptr.IsValidObject:
                        # Use the dynamic target parameter name passed from UI
                        p = row.view_ptr.LookupParameter(self.target_param)
                        if p and not p.IsReadOnly:
                            p.Set(self.new_value)
                t.Commit()
            
            # Silent Success (No Toast)
            
        except Exception as e:
            forms.alert("Transaction Failed: {}".format(e))

    def GetName(self):
        return "SubCatHandler"

# --- GLOBAL HANDLER INSTANTIATION ---
_handler = SubCatHandler()
_event = UI.ExternalEvent.Create(_handler)

# --- THE WINDOW ---
class ModelessSubCategorizer(object):
    def __init__(self):
        # XAML updated with RadioButtons and new Column
        xaml_str = """
        <Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
                Title="ViewSubCategorizer" Height="600" Width="1100" WindowStartupLocation="CenterScreen" Topmost="True">
            <Window.Resources>
                <Style TargetType="DataGridCell">
                    <Style.Triggers>
                        <Trigger Property="IsSelected" Value="True">
                            <Setter Property="Background" Value="#CCE8FF" /><Setter Property="Foreground" Value="Black" />
                        </Trigger>
                    </Style.Triggers>
                </Style>
            </Window.Resources>
            <Grid Margin="15">
                <Grid.RowDefinitions><RowDefinition Height="*"/><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
                
                <DataGrid Name="MainGrid" AutoGenerateColumns="False" CanUserAddRows="False" SelectionMode="Extended" SelectionUnit="FullRow" AlternatingRowBackground="#F9F9F9">
                    <DataGrid.Columns>
                        <DataGridTextColumn Header="View Name" Binding="{Binding name}" Width="2*" IsReadOnly="True"/>
                        <DataGridTextColumn Header="Tier 2 [Type Name]" Binding="{Binding t2_ootb}" Width="1.2*" IsReadOnly="True"/>
                        <DataGridTextColumn Header="Tier 2 [View.Type]" Binding="{Binding t2_custom}" Width="1.2*" IsReadOnly="True"/>
                        <DataGridTextColumn Header="Scale" Binding="{Binding view_scale}" Width="0.8*" IsReadOnly="True"/>
                        <DataGridTextColumn Header="Tier 3 [View.SubCategory]" Binding="{Binding t3}" Width="1.5*" IsReadOnly="True"/>
                        <DataGridTextColumn Header="Tier 3 [Source.Project]" Binding="{Binding t3_source}" Width="1.5*" IsReadOnly="True"/>
                    </DataGrid.Columns>
                </DataGrid>
                
                <StackPanel Grid.Row="1" Margin="0,15,0,10">
                    <StackPanel Orientation="Horizontal" Margin="0,0,0,5">
                        <TextBlock Text="Apply to: " FontWeight="Bold" VerticalAlignment="Center" Margin="0,0,10,0"/>
                        <RadioButton Name="RbSubCat" Content="View.SubCategory" GroupName="TargetParam" IsChecked="True" Margin="0,0,15,0" VerticalAlignment="Center"/>
                        <RadioButton Name="RbSource" Content="Source.Project" GroupName="TargetParam" VerticalAlignment="Center"/>
                    </StackPanel>
                    
                    <TextBlock Text="Select Value or Type New:" FontWeight="SemiBold" Margin="0,5,0,2"/>
                    <ComboBox Name="ValueInput" IsEditable="True" Height="32"/>
                </StackPanel>
                
                <Button Name="ApplyBtn" Grid.Row="2" Content="Apply Changes to Selected" Height="40" Background="#2196F3" Foreground="White" FontWeight="Bold"/>
                <Button Name="RefreshBtn" Grid.Row="3" Content="Update List from Selection" Height="30" Margin="0,10,0,0"/>
            </Grid>
        </Window>
        """
        reader = XmlReader.Create(StringReader(xaml_str))
        self.ui = XamlReader.Load(reader)
        
        # Element Binding
        self.grid = self.ui.FindName("MainGrid")
        self.combo = self.ui.FindName("ValueInput")
        self.apply_btn = self.ui.FindName("ApplyBtn")
        self.refresh_btn = self.ui.FindName("RefreshBtn")
        self.rb_subcat = self.ui.FindName("RbSubCat")
        self.rb_source = self.ui.FindName("RbSource")
        
        # Event Binding
        self.apply_btn.Click += self.on_apply
        self.refresh_btn.Click += self.on_refresh
        self.grid.SelectionChanged += self.on_selection_change
        
        # Bind RadioButtons to selection change so dropdown updates immediately if toggled
        self.rb_subcat.Checked += self.on_selection_change
        self.rb_source.Checked += self.on_selection_change
        
        self.load_data()
        
        try:
            handle = System.Diagnostics.Process.GetCurrentProcess().MainWindowHandle
            WindowInteropHelper(self.ui).Owner = handle
        except:
            pass

    def load_data(self):
        import Autodesk.Revit.DB as DB
        try:
            uidoc = revit.uidoc
            if uidoc:
                selection_ids = uidoc.Selection.GetElementIds()
                views = []
                for eid in selection_ids:
                    el = uidoc.Document.GetElement(eid)
                    if isinstance(el, DB.View):
                        views.append(el)
                
                self.grid.ItemsSource = [ViewRow(v) for v in views]
                self.grid.Items.Refresh()
        except Exception as e:
            print("Refresh Error: {}".format(e))

    def on_refresh(self, sender, e):
        self.load_data()

    def on_selection_change(self, sender, e):
        # 1. Thread Safety Imports
        import Autodesk.Revit.DB as DB
        
        # 2. Determine Active Parameter based on Radio Button
        # Defaults to SubCategory if check fails
        active_param = P_T3_SUBCAT 
        if self.rb_source.IsChecked:
            active_param = P_T3_SOURCE
            
        # 3. Populate Dropdown based on Active Parameter + View Type
        if self.grid.SelectedItems.Count > 0:
            try:
                row = self.grid.SelectedItems[0]
                ootb_type = row.t2_ootb
                doc = row.view_ptr.Document 
                
                all_v = DB.FilteredElementCollector(doc).OfClass(DB.View)
                vals = set()
                
                for v in all_v:
                    p_type = v.get_Parameter(DB.BuiltInParameter.ELEM_TYPE_PARAM)
                    # Filter: Only show values from views of the same "Type"
                    if p_type and p_type.AsValueString() == ootb_type:
                        p_target = v.LookupParameter(active_param)
                        if p_target and p_target.AsString():
                            vals.add(p_target.AsString())
                
                self.combo.ItemsSource = sorted(list(vals))
            except Exception as ex:
                print("Error in selection change: {}".format(ex))

    def on_apply(self, sender, e):
        try:
            new_val = str(self.combo.Text)
            
            # Determine Target Parameter
            target_param = P_T3_SUBCAT
            is_source = False
            if self.rb_source.IsChecked:
                target_param = P_T3_SOURCE
                is_source = True

            selected_rows = []
            for item in self.grid.SelectedItems:
                selected_rows.append(item)
                
                # OPTIMISTIC UPDATE: Update correct UI column immediately
                if is_source:
                    item.t3_source = new_val
                else:
                    item.t3 = new_val
            
            if not selected_rows:
                forms.alert("Please select rows in the grid first.")
                return

            # Pass data to global handler
            _handler.view_rows = selected_rows
            _handler.new_value = new_val
            _handler.target_param = target_param
            
            # Raise Event
            _event.Raise()
            
            # Refresh UI immediately
            self.grid.Items.Refresh()
            
        except Exception as ex:
            forms.alert("Apply Error: {}".format(ex))

    def show(self):
        self.ui.Show()

if __name__ == "__main__":
    main_window = ModelessSubCategorizer()
    main_window.show()
