# PolyForm Internal Use 1.0.0 - Copyright (C) 2026 Javier Sols
# Source available for inspection and authorized internal use only.

from pyrevit import revit, DB, forms
import clr
from System.Collections.Generic import List

doc = revit.doc
uidoc = revit.uidoc

# --- CONFIGURATION ---
# Removed VIEW_NAME_PREFIX as we are now stripping instead of adding
VIEW_TEMPLATE_NAME = "Standard Detail"
DATA_PARAMETER_NAME = "View.Type"
SEARCH_PARTICLE = "DTL"
# ---------------------

# 1. HARVEST DATA FROM ACTIVE VIEW
active_view = doc.ActiveView
active_scale_val = active_view.Scale
active_type_id = active_view.GetTypeId()
active_type_element = doc.GetElement(active_type_id)
active_type_name = active_type_element.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString()

# 2. Harvest all Drafting View Types
drafting_types = DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)
type_dict = {t.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString(): t 
             for t in drafting_types if t.ViewFamily == DB.ViewFamily.Drafting}

# 3. Setup Scales
scales = {
    '3/4" = 1\'-0"': 16,
    '1 1/2" = 1\'-0"': 8,
    '3" = 1\'-0"': 4,
    '1" = 1\'-0"': 12,
    '6" = 1\'-0"': 2,
    '12" = 1\'-0" (Full)': 1
}
default_scale_name = next((k for k, v in scales.items() if v == active_scale_val), '1 1/2" = 1\'-0"')

# 4. USER INPUTS
selected_scale_name = forms.ask_for_one_item(scales.keys(), default=default_scale_name, title="1. Confirm View Scale")
selected_type_name = forms.ask_for_one_item(sorted(type_dict.keys()), default=active_type_name, title="2. Confirm View Type") if selected_scale_name else None

if not selected_scale_name or not selected_type_name:
    print("Operation Cancelled.")
else:
    chosen_scale_value = scales[selected_scale_name]
    chosen_view_type = type_dict[selected_type_name]
    selection_ids = uidoc.Selection.GetElementIds()

    if not selection_ids:
        print("Error: Please select Detail Groups in your view.")
    else:
        view_templates = DB.FilteredElementCollector(doc).OfClass(DB.View)
        template = next((v for v in view_templates if v.IsTemplate and v.Name == VIEW_TEMPLATE_NAME), None)
        
        created_count = 0
        with revit.Transaction("CPG Library Clean Naming"):
            for el_id in selection_ids:
                el = doc.GetElement(el_id)
                if isinstance(el, DB.Group):
                    g_type = el.GroupType
                    g_name = g_type.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
                    
                    # --- NEW NAMING LOGIC ---
                    # Find 'DTL' and strip everything before it
                    dtl_index = g_name.find(SEARCH_PARTICLE)
                    if dtl_index != -1:
                        target_name = g_name[dtl_index:]
                    else:
                        target_name = g_name # Fallback if DTL isn't found
                    # ------------------------
                    
                    try:
                        new_view = DB.ViewDrafting.Create(doc, chosen_view_type.Id)
                        new_view.Name = target_name
                        
                        if template:
                            new_view.ViewTemplateId = template.Id
                            new_view.ViewTemplateId = DB.ElementId.InvalidElementId
                        
                        new_view.Scale = chosen_scale_value
                        
                        param = new_view.LookupParameter(DATA_PARAMETER_NAME)
                        if param:
                            param.Set(selected_type_name)
                        
                        ids_to_copy = List[DB.ElementId]()
                        ids_to_copy.Add(el.Id)
                        DB.ElementTransformUtils.CopyElements(active_view, ids_to_copy, new_view, DB.Transform.Identity, DB.CopyPasteOptions())
                        
                        created_count += 1
                        print("SUCCESS: {0} (from Group: {1})".format(target_name, g_name))
                    except Exception as e:
                        print("FAILED {0}: {1}".format(g_name, e))

        forms.alert("Process Complete!\nCreated {0} cleaned Drafting Views.".format(created_count))
