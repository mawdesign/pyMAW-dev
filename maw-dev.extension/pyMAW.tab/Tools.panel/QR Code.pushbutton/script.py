# -*- coding: UTF-8 -*-
from pyrevit import forms
from pyrevit import script
import sys
import pyqrcode

qrchars = " ▀▄█"  # ASCII box drawing

text = forms.ask_for_string(
    default="https://pyrevitlabs.notion.site",
    prompt="Enter QR code content:",
    title="Create Text QR Code",
    width=650,
)

if not text:
    script.exit()

qr = pyqrcode.create(text)

qrtext = []

for i in range(0, len(qr.code), 2):
    row = ""
    row1 = qr.code[i]
    row2 = qr.code[i + 1] if i + 1 < len(qr.code) else [0 for x in row1]
    for j in range(0, len(row1)):
        char = row1[j] + row2[j] * 2
        row += qrchars[char]
    qrtext.append(row)

print("\r\n".join(qrtext).replace(" ", u"\u00A0"))
print("\r\nQR Code copied to clipboard, paste into a text field to view.")

script.clipboard_copy("\r\n".join(qrtext))
