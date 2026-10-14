# WorkplaceTools.extension

A pyRevit extension for Autodesk Revit 2025 providing automation tools for
detail groups, drafting views, and sheet documentation workflows — developed
and maintained by Javier Sols.

## Tools

| # | Tool | Purpose |
|---|------|---------|
| 01 | DetailGroupToView | Converts selected placed detail groups into standalone drafting views with cleaned names, chosen scale, and view type metadata. |
| 02 | ViewSubCategorizer | Modeless manager for batch-editing `View.Type`, `View.SubCategory`, and `Source.Project` metadata across all drafting views. |
| 03 | ViewSourcetoSubCat | Modeless renamer that builds and applies standardized view names from source project, subcategory, and scale data. |
| 04 | DetailGroupNameSync | Synchronizes detail group names with their parent drafting views using a `DG_` naming convention. |
| 05 | SerialGrouping | Creates element groups with auto-incrementing serial names; supports pre-selection fast track and remembers your last naming configuration. |
| 06 | DetailGroupRenamer | Modeless batch renamer and cleaner for detail group type names model-wide. |
| 07 | SyncTitleonSheet | Synchronizes view names to the `Title on Sheet` parameter for selected views and viewports. |
| 08 | ToggleExcludeOptions | Toggles the Revit status-bar "Exclude Design Options" checkbox via UI Automation. Keyboard-shortcut friendly. |

## Installation

Install via the pyRevit ribbon installer by adding this repository as a
custom extension source, then enable the extension and reload pyRevit.

## License & Permitted Use

This software is licensed under the **PolyForm Internal Use License 1.0.0** —
see [LICENSE](LICENSE).

**Required Notice: Copyright (C) 2026 Javier Sols**

You are permitted to:

- **Inspect** the source code of this repository.
- **Use** the tools for the internal business operations of you and your
  company, via the pyRevit ribbon installer.

You are **not** permitted to:

- Sublicense or commercially resell the software or its source code.
- Extract, redistribute, or republish the underlying source code outside
  this repository.
- Transfer any of your licenses to anyone else.

For licensing inquiries beyond internal use, contact the copyright holder.
