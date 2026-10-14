# PolyForm Internal Use 1.0.0 - Copyright (C) 2026 Javier Sols
# Source available for inspection and authorized internal use only.

# -*- coding: utf-8 -*-
"""
ToggleExcludeOptions
Toggles the status-bar 'Exclude Design Options' checkbox.
Silent on success (no output window). Alerts only on failure.
Verified against Revit 2025.
"""

__title__ = "Toggle Exclude\nOptions"
__doc__ = "Toggles the status-bar 'Exclude Design Options' checkbox. Only active when the selection includes elements from design options (Revit shows the checkbox in those cases). Assign a keyboard shortcut via KS."

import traceback
import clr
from pyrevit import HOST_APP, forms

clr.AddReference("UIAutomationClient")
clr.AddReference("UIAutomationTypes")
from System.Windows.Automation import (AutomationElement, TreeScope,
                                       TogglePattern, PropertyCondition)

CHECKBOX_NAME = "Exclude Design Options"


def get_exclude_checkbox():
    """Find the 'Exclude Design Options' checkbox in Revit's main window.

    Uses Revit's API-provided main window handle (UIApplication.MainWindowHandle)
    - Process.MainWindowHandle would point at the pyRevit output window
    whenever that window is open.
    """
    root = AutomationElement.FromHandle(HOST_APP.uiapp.MainWindowHandle)
    return root.FindFirst(
        TreeScope.Descendants,
        PropertyCondition(AutomationElement.NameProperty, CHECKBOX_NAME))


try:
    cb = get_exclude_checkbox()
    if not cb:
        forms.alert("'Exclude Design Options' checkbox not found.\n\n"
                    "The checkbox only appears in the status bar while "
                    "elements belonging to design options are selected "
                    "(or hovered).\n\nOther causes:\n"
                    "- This document has no Design Options.\n"
                    "- Revit UI language is not English.",
                    title="Toggle Exclude Options", warn_icon=True,
                    exitscript=True)

    cb.GetCurrentPattern(TogglePattern.Pattern).Toggle()
except Exception:
    forms.alert("Toggle Exclude Options failed:\n\n{}".format(traceback.format_exc()),
                title="Toggle Exclude Options", warn_icon=True, exitscript=True)
