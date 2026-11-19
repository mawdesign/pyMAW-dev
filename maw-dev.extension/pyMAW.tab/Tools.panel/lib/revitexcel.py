# -*- coding: utf-8 -*-
"""Excel helpers built on pyrevit.interop.xl (xlrd for reading, xlsxwriter for writing)."""

# # ------------------ pyRevit Imports -------------------
import xlsxwriter
from pyrevit.interop import xl

__all__ = ["xlsxwriter", "ColourFormats", "cell_to_string", "read_workbook", "read_sheet"]


def cell_to_string(value):
    """Cell value -> stripped string. 12.0 -> "12", None/"none" -> ""."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return "" if text.lower() == "none" else text


def _to_table(sheet):
    """Convert one xl.load sheet to {"headers": [...], "rows": [dict, ...]}.

    Header names are stripped and lowercased; blank headers are ignored.
    Each row dict holds strings plus "_row", the Excel row number.
    """
    headers = [cell_to_string(h).lower() for h in sheet["headers"]]
    rows = []
    for index, values in enumerate(sheet["rows"], 2):
        row = {"_row": index}
        for header, value in zip(headers, values):
            if header:
                row[header] = cell_to_string(value)
        rows.append(row)
    return {"headers": [h for h in headers if h], "rows": rows}


def read_workbook(path, sheets=None):
    """Read an Excel file -> {sheet name: {"headers": [...], "rows": [...]}}.

    Sheet order is not preserved on IronPython 2.7, so sort names for display.
    """
    data = xl.load(path, sheets=sheets or [])
    return {name: _to_table(sheet) for name, sheet in data.items()}


def read_sheet(path, sheet_name):
    """Read a single sheet; returns None if the sheet does not exist."""
    return read_workbook(path, sheets=[sheet_name]).get(sheet_name)


class ColourFormats(object):
    """Cache of xlsxwriter cell formats filled with a colour."""

    def __init__(self, workbook):
        self._workbook = workbook
        self._formats = {}

    def get(self, hex_fill, hex_text):
        key = (hex_fill, hex_text)
        if key not in self._formats:
            self._formats[key] = self._workbook.add_format(
                {"bg_color": hex_fill, "font_color": hex_text}
            )
        return self._formats[key]
