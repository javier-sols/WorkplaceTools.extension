# PolyForm Internal Use 1.0.0 - Copyright (C) 2026 Javier Sols
# Source available for inspection and authorized internal use only.

"""
SerialGrouping v8.6
Revit 2025 / .NET 8 Stable
Feature: Pre-Selection Fast Track & IronPython Fixes
"""
__title__ = "Serial\nGrouping"

import clr
import System
import json
import os

# Explicit assembly loading
clr.AddReference('System.Xml')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('RevitAPI') 
clr.AddReference('RevitAPIUI')

from System.IO import StringReader
from System.Xml import XmlReader
from System.Windows.Markup import XamlReader
from System.Windows.Interop import WindowInteropHelper
from System.Collections.Generic import List

import Autodesk.Revit.DB as DB
import Autodesk.Revit.UI as UI_API
from pyrevit import revit, forms

from Autodesk.Revit.Exceptions import OperationCanceledException

# --- 1. CONFIGURATION PERSISTENCE ---
appdata_dir = os.environ.get('APPDATA', '')
CONFIG_PATH = os.path.join(appdata_dir, "pyRevit_SerialGrouping_v8.json")

def save_config(base_name, suffix):
    try:
        data = {"base_name": base_name, "suffix": suffix}
        with open(CONFIG_PATH, 'w') as f:
            json.dump(data, f)
    except:
        pass

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"base_name": "Detail_Group", "suffix": "01"}

# --- 2. DATA MODEL & HELPERS ---
class GroupHistoryRow(object):
    def __init__(self, name):
        self.name = name

# Bypasses the IronPython .Name reflection bug
def get_element_name(elem):
    try:
        return elem.Name
    except AttributeError:
        return DB.Element.Name.GetValue(elem)

def set_element_name(elem, target_name):
    try:
        elem.Name = target_name
    except AttributeError:
        DB.Element.Name.SetValue(elem, target_name)

# --- 3. THE UI WINDOW ---
class SerialGroupWindow(object):
    def __init__(self, start_base, start_suff, history_data):
        self.is_ready = False
        self.history_data = history_data
        
        xaml_str = """
        <Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
                Title="Serial Grouping v8.6" Height="550" Width="420" Topmost="True" WindowStartupLocation="CenterScreen">
            <Grid Margin="20">
                <Grid.RowDefinitions>
                    <RowDefinition Height="Auto"/><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/>
                </Grid.RowDefinitions>
                
                <StackPanel Grid.Row="0" Margin="0,0,0,15">
                    <TextBlock Text="NAMING CONFIGURATION" FontSize="10" FontWeight="Bold" Foreground="#666666"/>
                    <Separator Margin="0,5,0,5"/>
                </StackPanel>

                <Grid Grid.Row="1" Margin="0,0,0,15">
                    <Grid.ColumnDefinitions><ColumnDefinition Width="2*"/><ColumnDefinition Width="1*"/></Grid.ColumnDefinitions>
                    <StackPanel Margin="0,0,5,0">
                        <TextBlock Text="Base Name Particle:"/>
                        <TextBox Name="BaseNameInput" Height="28" VerticalContentAlignment="Center" FontSize="14"/>
                    </StackPanel>
                    <StackPanel Grid.Column="1" Margin="5,0,0,0">
                        <TextBlock Text="Start Suffix:"/>
                        <TextBox Name="SuffixInput" Height="28" VerticalContentAlignment="Center" FontSize="14"/>
                    </StackPanel>
                </Grid>

                <Button Name="StartBtn" Grid.Row="2" Content="START SERIAL GROUPING" Height="45" Background="#2E7D32" Foreground="White" FontWeight="Bold" FontSize="14"/>

                <GroupBox Grid.Row="3" Header="Session Confirmation History" Margin="0,15,0,0">
                    <DataGrid Name="HistoryGrid" AutoGenerateColumns="False" CanUserAddRows="False" IsReadOnly="True" Background="#F5F5F5" VerticalScrollBarVisibility="Auto">
                        <DataGrid.Columns>
                            <DataGridTextColumn Header="Created Group Name" Binding="{Binding name}" Width="*"/>
                        </DataGrid.Columns>
                    </DataGrid>
                </GroupBox>

                <StackPanel Grid.Row="4" Margin="0,15,0,0">
                    <TextBlock Text="INSTRUCTIONS:" FontWeight="Bold" FontSize="10" Foreground="#666666"/>
                    <TextBlock Text="1. Click Start. 2. Select elements. 3. Click 'Finish' on Options Bar." Foreground="#888888" FontSize="11" TextWrapping="Wrap"/>
                    <TextBlock Text="PRO TIP: Select elements before running script to bypass this UI." Foreground="#2196F3" FontSize="11" FontWeight="Bold" Margin="0,5,0,0"/>
                </StackPanel>
            </Grid>
        </Window>
        """
        reader = XmlReader.Create(StringReader(xaml_str))
        self.ui = XamlReader.Load(reader)
        
        self.base_input = self.ui.FindName("BaseNameInput")
        self.suffix_input = self.ui.FindName("SuffixInput")
        self.history_grid = self.ui.FindName("HistoryGrid")
        self.start_btn = self.ui.FindName("StartBtn")
        
        self.base_input.Text = start_base
        self.suffix_input.Text = start_suff
        self.history_grid.ItemsSource = self.history_data
        
        self.start_btn.Click += self.on_start_click
        
        try:
            handle = System.Diagnostics.Process.GetCurrentProcess().MainWindowHandle
            WindowInteropHelper(self.ui).Owner = handle
        except: pass

    def on_start_click(self, sender, e):
        self.base_val = self.base_input.Text
        self.suff_val = self.suffix_input.Text
        self.is_ready = True
        self.ui.Close()

    def show(self):
        self.ui.ShowDialog()

# --- 4. MAIN EXECUTION ---
if __name__ == "__main__":
    uidoc = revit.uidoc
    doc = revit.doc
    
    config = load_config()
    current_base = config.get("base_name", "Detail_Group")
    current_suff = config.get("suffix", "01")
    
    # Check for Pre-Selection
    pre_selection = uidoc.Selection.GetElementIds()
    
    # ==========================================
    # TRACK A: FAST TRACK (PRE-SELECTION MODE)
    # ==========================================
    if pre_selection.Count > 0:
        clean_suff = current_suff if current_suff.startswith("_") else "_" + current_suff
        target_name = "{}{}".format(current_base, clean_suff)
        
        with DB.Transaction(doc, "Serial Group: " + target_name) as t:
            t.Start()
            existing = DB.FilteredElementCollector(doc).OfClass(DB.GroupType)
            name_exists = any(get_element_name(et) == target_name for et in existing)
            
            if name_exists:
                t.RollBack()
                forms.alert("Error: '{}' already exists. Run tool without selection to change name.".format(target_name))
            else:
                try:
                    new_group = doc.Create.NewGroup(pre_selection)
                    set_element_name(new_group.GroupType, target_name)
                    t.Commit()
                    
                    # Increment & Save
                    numeric_part = "".join(filter(str.isdigit, current_suff))
                    if numeric_part:
                        next_val = int(numeric_part) + 1
                        current_suff = current_suff.replace(numeric_part, str(next_val).zfill(len(numeric_part)))
                    save_config(current_base, current_suff)
                    
                except Exception as e:
                    t.RollBack()
                    forms.alert("Failed to group elements.\nError: {}".format(e))
                    
    # ==========================================
    # TRACK B: CONFIG & LOOP (STANDARD MODE)
    # ==========================================
    else:
        session_history = []

        while True:
            app = SerialGroupWindow(current_base, current_suff, session_history)
            app.show()
            
            if not app.is_ready:
                break 
                
            current_base = app.base_val
            current_suff = app.suff_val
            save_config(current_base, current_suff)
            
            while True:
                clean_suff = current_suff if current_suff.startswith("_") else "_" + current_suff
                target_name = "{}{}".format(current_base, clean_suff)
                
                msg = "Select elements for {}. Click 'Finish' on Options Bar, or hit [ESC] to return.".format(target_name)
                
                try:
                    choices = uidoc.Selection.PickObjects(UI_API.Selection.ObjectType.Element, msg)
                except OperationCanceledException:
                    break

                if not choices or choices.Count == 0:
                    break

                ids = List[DB.ElementId]()
                for ref in choices:
                    ids.Add(ref.ElementId)

                with DB.Transaction(doc, "Serial Group: " + target_name) as t:
                    t.Start()
                    
                    existing = DB.FilteredElementCollector(doc).OfClass(DB.GroupType)
                    name_exists = any(get_element_name(et) == target_name for et in existing)
                    
                    if name_exists:
                        t.RollBack()
                        forms.alert("Error: '{}' already exists. Try incrementing manually.".format(target_name))
                        break 
                    else:
                        try:
                            new_group = doc.Create.NewGroup(ids)
                            set_element_name(new_group.GroupType, target_name)
                            t.Commit()
                            session_history.insert(0, GroupHistoryRow(target_name))
                        except Exception as e:
                            t.RollBack()
                            forms.alert("Failed to group elements.\nError: {}".format(e))
                            break
                        
                try:
                    numeric_part = "".join(filter(str.isdigit, current_suff))
                    if numeric_part:
                        next_val = int(numeric_part) + 1
                        current_suff = current_suff.replace(numeric_part, str(next_val).zfill(len(numeric_part)))
                except: 
                    pass
                    
                save_config(current_base, current_suff)
