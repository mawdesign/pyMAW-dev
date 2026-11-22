# -*- coding: utf-8 -*-
"""Moves a planting schedule when its Space Tag is edited.

register() subscribes to Application.DocumentChanged and is called only when
the landscape-tag or landscape-tag-update script runs. Nothing is loaded at
Revit startup. The calling script must set __persistentengine__ = True so the
handlers survive after the script finishes.

Cost control:
    - The event handler only asks Revit for modified Space Tags (category filter)
      and queues their ids. No document access happens inside the event.
    - Changes made by these scripts (transaction names starting with
      'Planting Tag:') are ignored, so the hook cannot trigger itself.
    - Queued ids are processed once per idle batch through an ExternalEvent,
      only against schedules on the sheets of the tags that changed.
    - A transaction is opened only if a schedule actually has to move.
    - The hook removes itself after repeated failures.
"""

# # -------------- Standard Library Imports --------------
import traceback

# # ------------------ pyRevit Imports -------------------
from pyrevit import revit, DB, UI, HOST_APP, script

# # ----------------- Autodesk Imports -------------------
from System import AppDomain, EventHandler
from Autodesk.Revit.DB.Events import DocumentChangedEventArgs

import landscape_tag_lib as lib

logger = script.get_logger()

STATE_KEY = "LANDSCAPE_TAG_HOOK"
OWN_TRANSACTION_PREFIX = "Planting Tag:"
FOLLOW_TRANSACTION_NAME = "Planting Tag: Follow tag"
MAX_FAILURES = 3
MOVE_TOLERANCE_FT = 1e-4


class HookState(object):
    def __init__(self):
        self.pending_ids = set()
        self.document = None
        self.failures = 0
        self.tag_filter = DB.ElementCategoryFilter(
            DB.ElementId(DB.BuiltInCategory.OST_MEPSpaceTags)
        )
        self.handler = None
        self.external_event = None
        self.delegate = None


def get_state():
    return AppDomain.CurrentDomain.GetData(STATE_KEY)


def find_follow_moves(doc, tag_id_values):
    tags = [doc.GetElement(DB.ElementId(value)) for value in tag_id_values]
    tags = [t for t in tags if isinstance(t, DB.Mechanical.SpaceTag)]
    viewport_by_view = dict(
        (vp.ViewId, vp)
        for vp in DB.FilteredElementCollector(doc).OfClass(DB.Viewport)
    )
    tag_by_id = dict(
        (lib.get_id_value(t.Id), t) for t in tags if t.OwnerViewId in viewport_by_view
    )
    if not tag_by_id:
        return []
    sheet_ids = set(
        viewport_by_view[t.OwnerViewId].SheetId for t in tag_by_id.values()
    )
    moves = []
    for instance in DB.FilteredElementCollector(doc).OfClass(
        DB.ScheduleSheetInstance
    ):
        if instance.OwnerViewId not in sheet_ids:
            continue
        linked = lib.get_schedule_tag(doc.GetElement(instance.ScheduleId))
        tag = tag_by_id.get(lib.get_id_value(linked.Id)) if linked else None
        if tag:
            view = doc.GetElement(tag.OwnerViewId)
            point = lib.schedule_point_for_tag(
                tag, view, viewport_by_view[tag.OwnerViewId]
            )
            if instance.Point.DistanceTo(point) > MOVE_TOLERANCE_FT:
                moves.append((instance, point))
    return moves


def follow_tags(doc, tag_id_values):
    moves = find_follow_moves(doc, tag_id_values)
    if not moves:
        return
    with revit.Transaction(FOLLOW_TRANSACTION_NAME):
        for instance, point in moves:
            instance.Point = point


class FollowTagsHandler(UI.IExternalEventHandler):
    def Execute(self, uiapp):
        state = get_state()
        if not state:
            return
        ids, state.pending_ids = state.pending_ids, set()
        doc = state.document
        if not ids or doc is None or not doc.Equals(revit.doc):
            return
        try:
            follow_tags(doc, ids)
            state.failures = 0
        except Exception:
            state.failures += 1
            logger.error(traceback.format_exc())
            if state.failures >= MAX_FAILURES:
                unregister(dispose_event=False)
                logger.warning("Landscape tag hook disabled after repeated errors.")

    def GetName(self):
        return "Landscape tag follow"


def on_document_changed(sender, args):
    state = get_state()
    if not state:
        return
    names = args.GetTransactionNames()
    if any(name.startswith(OWN_TRANSACTION_PREFIX) for name in names):
        return
    doc = args.GetDocument()
    if doc.IsFamilyDocument or doc.IsLinked:
        return
    changed = args.GetModifiedElementIds(state.tag_filter)
    if not changed.Count:
        return
    state.document = doc
    state.pending_ids.update(lib.get_id_value(i) for i in changed)
    state.external_event.Raise()


def register():
    unregister()
    state = HookState()
    state.handler = FollowTagsHandler()
    state.external_event = UI.ExternalEvent.Create(state.handler)
    state.delegate = EventHandler[DocumentChangedEventArgs](on_document_changed)
    HOST_APP.app.DocumentChanged += state.delegate
    AppDomain.CurrentDomain.SetData(STATE_KEY, state)


def unregister(dispose_event=True):
    state = get_state()
    if not state:
        return
    HOST_APP.app.DocumentChanged -= state.delegate
    if dispose_event:
        state.external_event.Dispose()
    AppDomain.CurrentDomain.SetData(STATE_KEY, None)
