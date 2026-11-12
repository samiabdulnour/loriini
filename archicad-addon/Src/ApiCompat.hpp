// The Archicad API calls whose spelling changed between versions, behind one
// name each.
//
// Archicad 27 replaced the old dispatchers -- ACAPI_Database (APIDb_...),
// ACAPI_Environment (APIEnv_...), ACAPI_Automate (APIDo_...), ACAPI_Interface
// (APIIo_...) -- with one named function per call, and 28 made an attribute
// index a class rather than an Int32. The commands call the functions below,
// and only this file knows which kit it is compiled against. Each one is the
// named function from 27 on and the dispatcher on 26, with the same arguments
// and the same error code, so nothing at a call site changes meaning.
//
// ServerMainVers_2700 is defined by every kit from 27 on, as each kit defines
// its own and every earlier one -- the test Tapir's commands use throughout.

#if !defined (LORIINI_APICOMPAT_HPP)
#define LORIINI_APICOMPAT_HPP

#pragma once

#include "APIEnvir.h"
#include "ACAPinc.h"

namespace Loriini {
namespace Api {

// --- Databases and windows --------------------------------------------------

inline GSErrCode GetCurrentDatabase (API_DatabaseInfo* database)
{
#ifdef ServerMainVers_2700
	return ACAPI_Database_GetCurrentDatabase (database);
#else
	return ACAPI_Database (APIDb_GetCurrentDatabaseID, database);
#endif
}

inline GSErrCode ChangeCurrentDatabase (API_DatabaseInfo* database)
{
#ifdef ServerMainVers_2700
	return ACAPI_Database_ChangeCurrentDatabase (database);
#else
	return ACAPI_Database (APIDb_ChangeCurrentDatabaseID, database);
#endif
}

inline GSErrCode NewDatabase (API_DatabaseInfo* database)
{
#ifdef ServerMainVers_2700
	return ACAPI_Database_NewDatabase (database);
#else
	return ACAPI_Database (APIDb_NewDatabaseID, database);
#endif
}

inline GSErrCode GetCurrentWindow (API_WindowInfo* window)
{
#ifdef ServerMainVers_2700
	return ACAPI_Window_GetCurrentWindow (window);
#else
	return ACAPI_Database (APIDb_GetCurrentWindowID, window);
#endif
}

inline GSErrCode ChangeWindow (API_WindowInfo* window)
{
#ifdef ServerMainVers_2700
	return ACAPI_Window_ChangeWindow (window);
#else
	return ACAPI_Automate (APIDo_ChangeWindowID, window);
#endif
}

// Rebuilds the front window, as the View > Refresh > Rebuild menu does;
// with ``regenerate``, as it does with the Option (Alt) key held.
inline GSErrCode RebuildFrontWindow (bool regenerate)
{
#ifdef ServerMainVers_2700
	return ACAPI_View_Rebuild (&regenerate);
#else
	return ACAPI_Automate (APIDo_RebuildID, &regenerate);
#endif
}

// --- Elements -----------------------------------------------------------------

inline GSErrCode GetElementInfoString (const API_Guid* guid, GS::UniString* identifier)
{
#ifdef ServerMainVers_2700
	return ACAPI_Element_GetElementInfoString (guid, identifier);
#else
	return ACAPI_Database (APIDb_GetElementInfoStringID, const_cast<API_Guid*> (guid), identifier);
#endif
}

inline GSErrCode ChangeElementInfoString (const API_Guid* guid, const GS::UniString* identifier)
{
#ifdef ServerMainVers_2700
	return ACAPI_Element_ChangeElementInfoString (guid, identifier);
#else
	return ACAPI_Database (APIDb_ChangeElementInfoStringID, const_cast<API_Guid*> (guid),
						   const_cast<GS::UniString*> (identifier));
#endif
}

// Bring to front, send to back and the rest: ACAPI_Element_Tool on 26, moved
// among the grouping calls in 27.
inline GSErrCode ElementTool (const GS::Array<API_Guid>& guids, API_ToolCmdID command, void* parameters)
{
#ifdef ServerMainVers_2700
	return ACAPI_Grouping_Tool (guids, command, parameters);
#else
	return ACAPI_Element_Tool (guids, command, parameters);
#endif
}

// --- Drawings -----------------------------------------------------------------

inline GSErrCode StartDrawingData ()
{
#ifdef ServerMainVers_2700
	return ACAPI_Drawing_StartDrawingData ();
#else
	return ACAPI_Database (APIDb_StartDrawingDataID);
#endif
}

inline GSErrCode StopDrawingData (GSPtr* drawingData, API_Box* bounds)
{
#ifdef ServerMainVers_2700
	return ACAPI_Drawing_StopDrawingData (drawingData, bounds);
#else
	return ACAPI_Database (APIDb_StopDrawingDataID, drawingData, bounds);
#endif
}

inline GSErrCode GetFullDrawingContentBox (API_Box* content, const API_Guid* drawing)
{
#ifdef ServerMainVers_2700
	return ACAPI_Drawing_GetFullDrawingContentBox (content, drawing);
#else
	return ACAPI_Database (APIDb_GetFullDrawingContentBoxID, content, const_cast<API_Guid*> (drawing));
#endif
}

// An element drawn as primitives, each handed to ``proc``.
inline GSErrCode ShapePrims (const API_Elem_Head& head, ShapePrimsProc* proc)
{
#ifdef ServerMainVers_2700
	return ACAPI_DrawingPrimitive_ShapePrims (head, proc);
#else
	return ACAPI_Element_ShapePrims (head, proc);
#endif
}

// --- 3D window and documents --------------------------------------------------

inline GSErrCode Get3DProjectionSets (API_3DProjectionInfo* info)
{
#ifdef ServerMainVers_2700
	return ACAPI_View_Get3DProjectionSets (info);
#else
	return ACAPI_Environment (APIEnv_Get3DProjectionSetsID, info);
#endif
}

inline GSErrCode Change3DProjectionSets (API_3DProjectionInfo* info)
{
#ifdef ServerMainVers_2700
	return ACAPI_View_Change3DProjectionSets (info);
#else
	return ACAPI_Environment (APIEnv_Change3DProjectionSetsID, info);
#endif
}

inline GSErrCode Get3DImageSets (API_3DFilterAndCutSettings* settings)
{
#ifdef ServerMainVers_2700
	return ACAPI_View_Get3DImageSets (settings);
#else
	return ACAPI_Environment (APIEnv_Get3DImageSetsID, settings);
#endif
}

inline GSErrCode Change3DImageSets (API_3DFilterAndCutSettings* settings, bool* convert)
{
#ifdef ServerMainVers_2700
	return ACAPI_View_Change3DImageSets (settings, convert);
#else
	return ACAPI_Environment (APIEnv_Change3DImageSetsID, settings, convert);
#endif
}

inline GSErrCode GetDocumentFrom3DSettings (API_DatabaseUnId* document, API_DocumentFrom3DType* settings)
{
#ifdef ServerMainVers_2700
	return ACAPI_View_GetDocumentFrom3DSettings (document, settings);
#else
	return ACAPI_Environment (APIEnv_GetDocumentFrom3DSettingsID, document, settings);
#endif
}

inline GSErrCode ChangeDocumentFrom3DSettings (API_DatabaseUnId* document, API_DocumentFrom3DType* settings)
{
#ifdef ServerMainVers_2700
	return ACAPI_View_ChangeDocumentFrom3DSettings (document, settings);
#else
	return ACAPI_Environment (APIEnv_ChangeDocumentFrom3DSettingsID, document, settings);
#endif
}

inline GSErrCode GetDocumentFrom3DDefaults (API_DocumentFrom3DDefaults* defaults)
{
#ifdef ServerMainVers_2700
	return ACAPI_View_GetDocumentFrom3DDefaults (defaults);
#else
	return ACAPI_Environment (APIEnv_GetDocumentFrom3DDefaultsID, defaults);
#endif
}

inline GSErrCode ChangeDocumentFrom3DDefaults (API_DocumentFrom3DDefaults* defaults)
{
#ifdef ServerMainVers_2700
	return ACAPI_View_ChangeDocumentFrom3DDefaults (defaults);
#else
	return ACAPI_Environment (APIEnv_ChangeDocumentFrom3DDefaultsID, defaults);
#endif
}

// --- The 3D model -------------------------------------------------------------

// ACAPI_3D_... on 26; from 27 the model is read through ACAPI_ModelAccess_...
// and the sight chosen through ACAPI_Sight_...

inline GSErrCode Get3DComponent (API_Component3D* component)
{
#ifdef ServerMainVers_2700
	return ACAPI_ModelAccess_GetComponent (component);
#else
	return ACAPI_3D_GetComponent (component);
#endif
}

inline GSErrCode Get3DCount (API_3DTypeID type, Int32* count)
{
#ifdef ServerMainVers_2700
	return ACAPI_ModelAccess_GetNum (type, count);
#else
	return ACAPI_3D_GetNum (type, count);
#endif
}

inline GSErrCode DecomposePgon (Int32 polygon, Int32*** contours)
{
#ifdef ServerMainVers_2700
	return ACAPI_ModelAccess_DecomposePgon (polygon, contours);
#else
	return ACAPI_3D_DecomposePgon (polygon, contours);
#endif
}

inline GSErrCode GetCurrentWindowSight (void** sight)
{
#ifdef ServerMainVers_2700
	return ACAPI_Sight_GetCurrentWindowSight (sight);
#else
	return ACAPI_3D_GetCurrentWindowSight (sight);
#endif
}

inline GSErrCode SelectSight (void* sight, void** previous)
{
#ifdef ServerMainVers_2700
	return ACAPI_Sight_SelectSight (sight, previous);
#else
	return ACAPI_3D_SelectSight (sight, previous);
#endif
}

// --- Project settings ---------------------------------------------------------

inline GSErrCode GetStorySettings (API_StoryInfo* info)
{
#ifdef ServerMainVers_2700
	return ACAPI_ProjectSetting_GetStorySettings (info);
#else
	return ACAPI_Environment (APIEnv_GetStorySettingsID, info);
#endif
}

inline GSErrCode GetPlaceSets (API_PlaceInfo* place)
{
#ifdef ServerMainVers_2700
	return ACAPI_GeoLocation_GetPlaceSets (place);
#else
	return ACAPI_Environment (APIEnv_GetPlaceSetsID, place);
#endif
}

inline GSErrCode ChangeCurrentLayerCombination (API_AttributeIndex* index)
{
#ifdef ServerMainVers_2700
	return ACAPI_Navigator_ChangeCurrLayerComb (index);
#else
	return ACAPI_Environment (APIEnv_ChangeCurrLayerCombID, index);
#endif
}

inline GSErrCode GetOverrideCombinationList (GS::Array<API_Guid>& guids)
{
#ifdef ServerMainVers_2700
	return ACAPI_GraphicalOverride_GetOverrideCombinationList (guids);
#else
	return ACAPI_Override_GetOverrideCombinationList (guids);
#endif
}

inline GSErrCode GetOverrideCombination (API_OverrideCombination& combination)
{
#ifdef ServerMainVers_2700
	return ACAPI_GraphicalOverride_GetOverrideCombination (combination);
#else
	return ACAPI_Override_GetOverrideCombination (combination);
#endif
}

// --- IFC export -----------------------------------------------------------------

// The project saved as IFC through a translator chosen by the caller. 26 has
// it behind the Automate dispatcher; 27 on as an overload of its own.
inline GSErrCode SaveAsIfc (const API_FileSavePars* file, const API_SavePars_Ifc* ifc)
{
#ifdef ServerMainVers_2700
	return ACAPI_ProjectOperation_Save (file, ifc);
#else
	return ACAPI_Automate (APIDo_SaveID, const_cast<API_FileSavePars*> (file), const_cast<API_SavePars_Ifc*> (ifc));
#endif
}

// --- Renovation filters ---------------------------------------------------------

inline GSErrCode GetRenovationFilters (GS::Array<API_Guid>* filters)
{
#ifdef ServerMainVers_2700
	return ACAPI_Renovation_GetRenovationFilters (filters);
#else
	return ACAPI_Database (APIDb_GetRenovationFiltersID, filters);
#endif
}

inline GSErrCode GetRenovationFilterName (const API_Guid* filter, GS::UniString* name)
{
#ifdef ServerMainVers_2700
	return ACAPI_Renovation_GetRenovationFilterName (filter, name);
#else
	return ACAPI_Goodies (APIAny_GetRenovationFilterNameID, const_cast<API_Guid*> (filter), name);
#endif
}

inline GSErrCode GetActualRenovationFilter (API_Guid* filter)
{
#ifdef ServerMainVers_2700
	return ACAPI_Renovation_GetActualRenovationFilter (filter);
#else
	return ACAPI_Database (APIDb_GetActualRenovationFilterID, filter);
#endif
}

inline GSErrCode SetActualRenovationFilter (const API_Guid* filter)
{
#ifdef ServerMainVers_2700
	return ACAPI_Renovation_SetActualRenovationFilter (filter);
#else
	return ACAPI_Database (APIDb_SetActualRenovationFilterID, const_cast<API_Guid*> (filter));
#endif
}

// --- Menus ----------------------------------------------------------------------

inline GSErrCode RegisterMenu (short menu, short prompt, APIMenuCodeID position, GSFlags flags)
{
#ifdef ServerMainVers_2700
	return ACAPI_MenuItem_RegisterMenu (menu, prompt, position, flags);
#else
	return ACAPI_Register_Menu (menu, prompt, position, flags);
#endif
}

inline GSErrCode InstallMenuHandler (short menu, APIMenuCommandProc* handler)
{
#ifdef ServerMainVers_2700
	return ACAPI_MenuItem_InstallMenuHandler (menu, handler);
#else
	return ACAPI_Install_MenuHandler (menu, handler);
#endif
}

inline GSErrCode GetMenuItemFlags (API_MenuItemRef* item, GSFlags* flags)
{
#ifdef ServerMainVers_2700
	return ACAPI_MenuItem_GetMenuItemFlags (item, flags);
#else
	return ACAPI_Interface (APIIo_GetMenuItemFlagsID, item, flags);
#endif
}

inline GSErrCode SetMenuItemFlags (API_MenuItemRef* item, GSFlags* flags)
{
#ifdef ServerMainVers_2700
	return ACAPI_MenuItem_SetMenuItemFlags (item, flags);
#else
	return ACAPI_Interface (APIIo_SetMenuItemFlagsID, item, flags);
#endif
}

// --- JSON commands -------------------------------------------------------------

inline GSErrCode InstallAddOnCommandHandler (GS::Owner<API_AddOnCommand> command)
{
#ifdef ServerMainVers_2700
	return ACAPI_AddOnAddOnCommunication_InstallAddOnCommandHandler (std::move (command));
#else
	return ACAPI_Install_AddOnCommandHandler (std::move (command));
#endif
}

// --- Attribute indices ----------------------------------------------------------

// A plain number, as the Python side sends and reads one. From 27 an index is
// a class, and these are the conversions its kit provides for code that still
// speaks in numbers.
inline Int32 AttributeIndexToInt (const API_AttributeIndex& index)
{
#ifdef ServerMainVers_2700
	return index.ToInt32_Deprecated ();
#else
	return static_cast<Int32> (index);
#endif
}

inline API_AttributeIndex AttributeIndexFromInt (Int32 index)
{
#ifdef ServerMainVers_2700
	return ACAPI_CreateAttributeIndex (index);
#else
	return static_cast<API_AttributeIndex> (index);
#endif
}

} // namespace Api
} // namespace Loriini

#endif
