"""Where the research data lives.

The gym code ships in the kahvibot repo; its data does not: the frame archive
(20k guild-room frames), the crop caches and hand-click labels in _work/, and the
training checkpoints all live in the coffee_mesh_pred research checkout. Point
COFFEE_RESEARCH_DIR at that checkout; the default is a sibling directory of this
repo named coffee_mesh_pred. The deployed ONNX bundle is in reader/models and
needs none of this.
"""
from __future__ import annotations

import os
from pathlib import Path

KAHVIBOT = Path(__file__).resolve().parents[2]            # this repo
RESEARCH = Path(os.environ.get("COFFEE_RESEARCH_DIR") or (KAHVIBOT.parent / "coffee_mesh_pred"))
WORK = RESEARCH / "_work"                                 # labels, caches, checkpoints, onnx_<tag>/
ARCHIVE = RESEARCH / "raw_img"                            # archived camera frames
COFFEE_ROOT = RESEARCH.parent                             # kahviraspi_logs_*/, coffee_images/
