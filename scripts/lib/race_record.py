"""Typed race record extracted from racialtypes.2da."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import rollnw

from .tlk import TlkResolver
from .spell_record import _icon_cell


def _norm(v: Optional[str]) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s == "****":
        return ""
    return s


def _opt_int(v: Optional[str]) -> Optional[int]:
    s = _norm(v)
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _bool(s: str) -> Optional[bool]:
    if s == "":
        return None
    try:
        return bool(int(s))
    except (ValueError, TypeError):
        return None


def _signed(n: Optional[int]) -> str:
    """Display ability adjustments with explicit sign: '+2', '-2', '0'."""
    if n is None:
        return ""
    if n > 0:
        return f"+{n}"
    return str(n)


@dataclass
class RaceRecord:
    label: str = ""
    abrev: str = ""
    name: str = ""
    name_strref: str = ""
    name_plural: str = ""
    name_plural_strref: str = ""
    description: str = ""
    description_strref: str = ""
    icon: str = ""
    appearance: str = ""
    str_adjust: Optional[int] = None
    dex_adjust: Optional[int] = None
    con_adjust: Optional[int] = None
    int_adjust: Optional[int] = None
    wis_adjust: Optional[int] = None
    cha_adjust: Optional[int] = None
    endurance: Optional[int] = None
    favored: str = ""  # row index into classes.2da
    favored_name: str = ""  # resolved by xref linker
    feats_table: str = ""
    biography: str = ""
    biography_strref: str = ""
    player_race: Optional[bool] = None
    constant: str = ""
    age: str = ""
    cr_modifier: str = ""

    @classmethod
    def from_2da_row(cls, tda: rollnw.TwoDA, row: int, tlk: TlkResolver) -> "RaceRecord":
        get = lambda c: _norm(tda.get_raw(row, tda.column_index(c)))
        gi = lambda c: _opt_int(tda.get_raw(row, tda.column_index(c)))
        return cls(
            label=get("Label"),
            abrev=get("Abrev"),
            name=tlk.must_get(get("Name")) if get("Name") else "",
            name_strref=get("Name"),
            name_plural=tlk.must_get(get("NamePlural")) if get("NamePlural") else "",
            name_plural_strref=get("NamePlural"),
            description=tlk.must_get(get("Description")) if get("Description") else "",
            description_strref=get("Description"),
            icon=get("Icon"),
            appearance=get("Appearance"),
            str_adjust=gi("StrAdjust"),
            dex_adjust=gi("DexAdjust"),
            con_adjust=gi("ConAdjust"),
            int_adjust=gi("IntAdjust"),
            wis_adjust=gi("WisAdjust"),
            cha_adjust=gi("ChaAdjust"),
            endurance=gi("Endurance"),
            favored=get("Favored"),
            feats_table=get("FeatsTable"),
            biography=tlk.must_get(get("Biography")) if get("Biography") else "",
            biography_strref=get("Biography"),
            player_race=_bool(get("PlayerRace")),
            constant=get("Constant"),
            age=get("AGE"),
            cr_modifier=get("CRModifier"),
        )

    def is_real_race(self) -> bool:
        if not self.label or not self.name:
            return False
        if self.label.startswith(("DEL_", "PADDING_", "DELETED_", "Reserved_")):
            return False
        return True

    @staticmethod
    def yes_no(b: Optional[bool]) -> str:
        if b is None:
            return ""
        return "Yes" if b else "No"

    def ability_adjustments(self) -> str:
        """Render ability adjustments as a compact list, omitting zero-effect rows."""
        pairs = [
            ("STR", self.str_adjust), ("DEX", self.dex_adjust),
            ("CON", self.con_adjust), ("INT", self.int_adjust),
            ("WIS", self.wis_adjust), ("CHA", self.cha_adjust),
        ]
        parts = [f"{label} {_signed(v)}" for label, v in pairs if v not in (None, 0)]
        return ", ".join(parts) if parts else "None"


def _favored_xref(name: str, raw: str) -> str:
    if name:
        return f"[[{name}]]"
    if raw:
        return f"<code>class#{raw}</code>"
    return ""


RACE_DISPLAY_FIELDS: list[tuple[str, callable]] = [
    ("Name", lambda r: r.name),
    ("Plural", lambda r: r.name_plural),
    ("Player Race", lambda r: r.yes_no(r.player_race)),
    ("Ability Adjustments", lambda r: r.ability_adjustments()),
    ("Endurance", lambda r: "" if r.endurance is None else str(r.endurance)),
    ("Favored Class", lambda r: _favored_xref(r.favored_name, r.favored)),
    ("Adult Age", lambda r: r.age),
    ("CR Modifier", lambda r: r.cr_modifier),
    ("Feats Table", lambda r: f"<code>{r.feats_table}</code>" if r.feats_table else ""),
    ("Script Constant", lambda r: f"<code>{r.constant}</code>" if r.constant else ""),
    ("Icon", lambda r: _icon_cell(r.icon)),
    ("Description", lambda r: r.description),
    ("Biography", lambda r: r.biography),
]


def link_race_xrefs(races: dict[str, "RaceRecord"],
                    id_maps: dict[str, dict[int, str]]) -> None:
    """Resolve `Favored` (row in classes.2da) to a class name link."""
    class_id_to_name = id_maps.get("class", {})

    def _lookup(raw: str) -> str:
        try:
            return class_id_to_name.get(int(raw), "")
        except (ValueError, TypeError):
            return ""
    for rr in races.values():
        rr.favored_name = _lookup(rr.favored)


def load_races(twoda_path, tlk: TlkResolver) -> tuple[dict[str, "RaceRecord"], dict[int, str]]:
    with open(twoda_path) as f:
        tda = rollnw.TwoDA.from_string(f.read())
    out: dict[str, RaceRecord] = {}
    id_to_name: dict[int, str] = {}
    for r in range(tda.rows()):
        rec = RaceRecord.from_2da_row(tda, r, tlk)
        if rec.name:
            id_to_name[r] = rec.name
        if rec.is_real_race():
            out[rec.label] = rec
    return out, id_to_name
