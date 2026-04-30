"""Load masterfeats.2da into a {row_id: resolved_name} map."""
from __future__ import annotations

import rollnw

from .tlk import TlkResolver


def load_masterfeats(twoda_path, tlk: TlkResolver) -> dict[int, str]:
    with open(twoda_path) as f:
        tda = rollnw.TwoDA.from_string(f.read())
    out: dict[int, str] = {}
    strref_col = tda.column_index("STRREF")
    for r in range(tda.rows()):
        v = tda.get_raw(r, strref_col)
        name = tlk.must_get(v) if v and v != "****" else ""
        if name:
            out[r] = name
    return out
