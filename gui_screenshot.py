#!/usr/bin/env python3
"""Capture a screenshot of the GUI preview using Qt's offscreen renderer."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSize

app = QApplication(sys.argv)

from gui_preview import PreviewWindow

window = PreviewWindow()
window.resize(QSize(960, 700))
window.show()

# Grab the window and save
pixmap = window.grab()
pixmap.save("gui_preview_initial.png")

# Step 2: simulate moving to a puzzle room
window._on_command(type("Cmd", (), {"verb": "go", "args": ["E"]})())
pixmap2 = window.grab()
pixmap2.save("gui_preview_puzzle.png")

# Step 3: show hint options
window._on_hint("")
pixmap3 = window.grab()
pixmap3.save("gui_preview_hints.png")

# Step 4: show completion
window._step = 4
window._on_command(type("Cmd", (), {"verb": "go", "args": ["E"]})())
pixmap4 = window.grab()
pixmap4.save("gui_preview_complete.png")

print("Screenshots saved:")
for f in ["gui_preview_initial.png", "gui_preview_puzzle.png",
          "gui_preview_hints.png", "gui_preview_complete.png"]:
    print(f"  {f}")
