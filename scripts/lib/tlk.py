"""TLK string resolution for both stock dialog.tlk and the custom layonara.tlk.

Custom TLK strings live at offset 16777216 and above (subtract to get the row in
layonara.tlk.json). Anything below that offset is a stock dialog.tlk row.
"""
from __future__ import annotations

import json
from pathlib import Path

CUSTOM_TLK_OFFSET = 16_777_216


class TlkResolver:
    def __init__(self, stock_path: Path, custom_path: Path):
        self._stock = self._load(stock_path)
        self._custom = self._load(custom_path)

    @staticmethod
    def _load(path) -> dict[int, str]:
        with open(path) as f:
            data = json.load(f)
        return {e["id"]: e["text"] for e in data["entries"]}

    def get(self, strref: int | str) -> str | None:
        if strref is None or strref == "" or strref == "****":
            return None
        try:
            sid = int(strref)
        except (TypeError, ValueError):
            return None
        if sid >= CUSTOM_TLK_OFFSET:
            row = sid - CUSTOM_TLK_OFFSET
            return self._custom.get(row)
        return self._stock.get(sid)

    def must_get(self, strref: int | str, default: str = "") -> str:
        v = self.get(strref)
        return v if v is not None else default

    def is_custom(self, strref: int | str) -> bool:
        try:
            return int(strref) >= CUSTOM_TLK_OFFSET
        except (TypeError, ValueError):
            return False
