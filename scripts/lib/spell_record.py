"""Typed spell record extracted from spells.2da, with field-level diff against stock."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Iterable, Optional

import rollnw

from .tlk import TlkResolver


# Per https://nwn.wiki/spaces/NWN1/pages/38175046/spells.2da
SCHOOL_NAMES = {
    "A": "Abjuration", "C": "Conjuration", "D": "Divination", "E": "Enchantment",
    "V": "Evocation", "I": "Illusion", "N": "Necromancy", "T": "Transmutation",
    "G": "General",
}
# Range letters map to hardcoded distances in meters.
RANGE_INFO = {
    "P": ("Personal", 0.0),
    "T": ("Touch", 2.25),
    "S": ("Short", 8.0),
    "M": ("Medium", 20.0),
    "L": ("Long", 40.0),
}
COMPONENTS_NAMES = {
    "v": "Verbal", "s": "Somatic", "vs": "Verbal, Somatic", "sv": "Verbal, Somatic", "": "None",
}
# Bitwise flags
METAMAGIC_BITS = [
    (0x01, "Empower"), (0x02, "Extend"), (0x04, "Maximize"),
    (0x08, "Quicken"), (0x10, "Silent"), (0x20, "Still"),
]
TARGET_TYPE_BITS = [
    (0x01, "Self"), (0x02, "Creature"), (0x04, "Area / Ground"), (0x08, "Items"),
    (0x10, "Door"), (0x20, "Placeable"), (0x40, "Trigger"),
]
TARGET_FLAG_BITS = [
    (0x01, "Harms Enemies"), (0x02, "Harms Allies"), (0x04, "Helps Allies"),
    (0x08, "Ignores Self"), (0x10, "Origin on Self"), (0x20, "Suppress with Target"),
]
TARGET_SHAPE_NAMES = {
    "sphere": "Sphere",
    "cone": "Cone",
    "rectangle": "Rectangle / Cylinder",
    "hsphere": "Hollow Sphere (donut)",
}
USER_TYPE_NAMES = {
    "1": "Spell", "2": "Creature Power", "3": "Feat", "4": "Item Power",
}


def _decode_bitmask(value_str: str, bits: list[tuple[int, str]]) -> str:
    """Decode '0x3E' or '62' style bitmask into a comma-joined name list."""
    if not value_str:
        return ""
    try:
        v = int(value_str, 0)  # accepts 0x prefix and decimal
    except ValueError:
        return value_str
    if v == 0:
        return "None"
    parts = [name for bit, name in bits if v & bit]
    return ", ".join(parts) if parts else f"(unknown: {value_str})"

CLASS_COLUMNS = ["Bard", "Cleric", "Druid", "Paladin", "Ranger", "Wiz_Sorc", "Innate"]
CLASS_DISPLAY = {
    "Bard": "Bard",
    "Cleric": "Cleric",
    "Druid": "Druid",
    "Paladin": "Paladin",
    "Ranger": "Ranger",
    "Wiz_Sorc": "Wizard / Sorcerer",
    "Innate": "Innate",
}


def _norm(v: Optional[str]) -> str:
    """Normalize a 2da cell value: empty / **** / None -> ''."""
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


@dataclass
class SpellRecord:
    label: str = ""
    name: str = ""
    name_strref: str = ""
    school: str = ""
    school_letter: str = ""
    innate_level: Optional[int] = None
    class_levels: dict[str, Optional[int]] = field(default_factory=dict)
    components: str = ""
    components_raw: str = ""
    range_: str = ""
    range_letter: str = ""
    range_meters: Optional[float] = None
    target_types: str = ""
    target_type_raw: str = ""
    target_shape: str = ""
    target_shape_raw: str = ""
    target_size_x: str = ""
    target_size_y: str = ""
    target_flags: str = ""
    target_flags_raw: str = ""
    cast_time_ms: Optional[int] = None
    conj_time_ms: Optional[int] = None
    user_type: str = ""
    user_type_raw: str = ""
    hostile: Optional[bool] = None
    use_concentration: Optional[bool] = None
    spontaneously_cast: Optional[bool] = None
    metamagic: str = ""
    metamagic_raw: str = ""
    impact_script: str = ""
    icon_resref: str = ""
    description: str = ""
    description_strref: str = ""
    sub_radial: list[str] = field(default_factory=list)
    master_spell: str = ""
    feat_id: str = ""

    # Resolved cross-references (filled in by link_xrefs after loading both 2das).
    sub_radial_names: list[str] = field(default_factory=list)
    master_spell_name: str = ""
    feat_id_name: str = ""

    @classmethod
    def from_2da_row(cls, tda: rollnw.TwoDA, row: int, tlk: TlkResolver) -> "SpellRecord":
        get = lambda c: _norm(tda.get_raw(row, tda.column_index(c)))
        gi = lambda c: _opt_int(tda.get_raw(row, tda.column_index(c)))

        school_letter = get("School")
        components_raw = get("VS")
        range_letter = get("Range").upper()
        range_name, range_meters = RANGE_INFO.get(range_letter, (range_letter, None))
        tt_raw = get("TargetType")
        ts_raw = get("TargetShape").lower()
        tf_raw = get("TargetFlags")
        ut_raw = get("UserType")
        mm_raw = get("MetaMagic")

        sub_radial = []
        for col in ("SubRadSpell1", "SubRadSpell2", "SubRadSpell3", "SubRadSpell4", "SubRadSpell5"):
            v = get(col)
            if v:
                sub_radial.append(v)

        cls_levels: dict[str, Optional[int]] = {}
        for c in CLASS_COLUMNS:
            cls_levels[c] = gi(c)

        def _bool(s):
            return None if s == "" else bool(int(s))

        return cls(
            label=get("Label"),
            name=tlk.must_get(get("Name")) if get("Name") else "",
            name_strref=get("Name"),
            school=SCHOOL_NAMES.get(school_letter, school_letter),
            school_letter=school_letter,
            innate_level=gi("Innate"),
            class_levels=cls_levels,
            components=COMPONENTS_NAMES.get(components_raw.lower(), components_raw),
            components_raw=components_raw,
            range_=range_name,
            range_letter=range_letter,
            range_meters=range_meters,
            target_types=_decode_bitmask(tt_raw, TARGET_TYPE_BITS),
            target_type_raw=tt_raw,
            target_shape=TARGET_SHAPE_NAMES.get(ts_raw, ts_raw or ""),
            target_shape_raw=ts_raw,
            target_size_x=get("TargetSizeX"),
            target_size_y=get("TargetSizeY"),
            target_flags=_decode_bitmask(tf_raw, TARGET_FLAG_BITS),
            target_flags_raw=tf_raw,
            cast_time_ms=gi("CastTime"),
            conj_time_ms=gi("ConjTime"),
            user_type=USER_TYPE_NAMES.get(ut_raw, ut_raw),
            user_type_raw=ut_raw,
            hostile=_bool(get("HostileSetting")),
            use_concentration=_bool(get("UseConcentration")),
            spontaneously_cast=_bool(get("SpontaneouslyCast")),
            metamagic=_decode_bitmask(mm_raw, METAMAGIC_BITS),
            metamagic_raw=mm_raw,
            impact_script=get("ImpactScript"),
            icon_resref=get("IconResRef"),
            description=tlk.must_get(get("SpellDesc")) if get("SpellDesc") else "",
            description_strref=get("SpellDesc"),
            sub_radial=sub_radial,
            master_spell=get("Master"),
            feat_id=get("FeatID"),
        )

    def is_real_spell(self) -> bool:
        """Filter out 2da padding/placeholder rows."""
        if not self.label:
            return False
        if self.label.startswith(("DEL_", "PADDING_", "Reserved_", "DELETED_")):
            return False
        if not self.name:
            return False
        return True

    # ---- public-facing field rendering ----

    def class_progression(self) -> str:
        parts = []
        for c in CLASS_COLUMNS:
            lvl = self.class_levels.get(c)
            if lvl is not None:
                parts.append(f"{CLASS_DISPLAY[c]} {lvl}")
        return ", ".join(parts) if parts else "None"

    def aoe(self) -> str:
        if not self.target_shape:
            return ""
        # Sphere: x is radius. Rectangle/cylinder: x is X-size, y is Y-size.
        # Hsphere: x is inner radius, y is outer.
        sx, sy = self.target_size_x, self.target_size_y
        shape = self.target_shape
        if self.target_shape_raw == "sphere" and sx:
            return f"{shape}, {sx}m radius"
        if self.target_shape_raw == "cone" and sx:
            return f"{shape}, {sx}m long"
        if self.target_shape_raw == "rectangle" and sx and sy:
            return f"{shape}, {sx}m \u00d7 {sy}m"
        if self.target_shape_raw == "hsphere" and sx and sy:
            return f"{shape}, inner {sx}m / outer {sy}m"
        size = (sx + (f" \u00d7 {sy}" if sy else "")).strip()
        return f"{shape}" + (f" ({size})" if size else "")

    def range_display(self) -> str:
        if not self.range_:
            return ""
        if self.range_meters is not None:
            return f"{self.range_} ({self.range_meters:g}m)"
        return self.range_

    def cast_time_seconds(self) -> str:
        if self.cast_time_ms is None:
            return ""
        return f"{self.cast_time_ms / 1000:g}s"

    def conj_time_seconds(self) -> str:
        if self.conj_time_ms is None:
            return ""
        return f"{self.conj_time_ms / 1000:g}s"

    def yes_no(self, b: Optional[bool]) -> str:
        if b is None:
            return ""
        return "Yes" if b else "No"


# --- icon rendering ----------------------------------------------------------
# `wiki_sync.py` calls set_known_icon_files() at startup with the set of icon
# filenames (lowercase, including ".png" suffix) that actually exist on the
# wiki. _icon_cell consults that set: if the file is missing, it degrades to a
# plain `<code>resref</code>` cell instead of emitting a broken-image link.
# When the set is empty (default), icons are always emitted -- preserves the
# old behaviour for tests and ad-hoc renders.
_KNOWN_ICONS: set[str] = set()


def set_known_icon_files(filenames: set[str]) -> None:
    """Configure the icon-existence whitelist (lowercase `<resref>.png` strings).
    Pass an empty set to disable the check (always emit `[[File:...]]`)."""
    global _KNOWN_ICONS
    _KNOWN_ICONS = {f.lower() for f in filenames}


# (label, getter) — order defines wikitable row order.
def _icon_cell(resref: str) -> str:
    """Render the icon cell for the autosync table.

    Wiki convention: icon files are uploaded as `<resref>.png` (lowercase).
    MediaWiki normalises the first character automatically. Empty resref ->
    empty cell so identical-stock blocks stay tidy.

    If `set_known_icon_files()` has been populated and `<resref>.png` is not in
    it, render the resref alone (no `[[File:...]]`) so missing/typo'd icons
    don't leave broken-image links on the page.
    """
    if not resref:
        return ""
    fname = resref.lower() + ".png"
    code = f"<code>{resref}</code>"
    if _KNOWN_ICONS and fname not in _KNOWN_ICONS:
        return code
    return f"[[File:{fname}|frameless|64px|border|alt={resref}]] {code}"


def _spell_xref(name: str, raw: str, kind: str = "spell") -> str:
    if name:
        return f"[[{name}]]"
    if not raw:
        return ""
    return f"<code>{kind}#{raw}</code>"


def _sub_radial_display(s: "SpellRecord") -> str:
    if not s.sub_radial:
        return ""
    parts = []
    for raw, name in zip(s.sub_radial,
                         s.sub_radial_names + [""] * len(s.sub_radial)):
        parts.append(_spell_xref(name, raw))
    return ", ".join(parts)


SPELL_DISPLAY_FIELDS: list[tuple[str, callable]] = [
    ("Name", lambda s: s.name),
    ("School", lambda s: s.school),
    ("Innate Level", lambda s: "" if s.innate_level is None else str(s.innate_level)),
    ("Class Progression", lambda s: s.class_progression()),
    ("Components", lambda s: s.components),
    ("Range", lambda s: s.range_display()),
    ("Valid Targets", lambda s: s.target_types),
    ("Area of Effect", lambda s: s.aoe()),
    ("Targeting Flags", lambda s: s.target_flags),
    ("Conjuration Time", lambda s: s.conj_time_seconds()),
    ("Casting Time", lambda s: s.cast_time_seconds()),
    ("Hostile", lambda s: s.yes_no(s.hostile)),
    ("Uses Concentration", lambda s: s.yes_no(s.use_concentration)),
    ("Spontaneously Cast", lambda s: s.yes_no(s.spontaneously_cast)),
    ("Allowed Metamagic", lambda s: s.metamagic),
    ("Spell Type", lambda s: s.user_type),
    ("Master Spell", lambda s: _spell_xref(s.master_spell_name, s.master_spell)),
    ("Sub-Radial Spells", _sub_radial_display),
    ("Triggering Feat", lambda s: _spell_xref(s.feat_id_name, s.feat_id, kind="feat")),
    ("Impact Script", lambda s: f"<code>{s.impact_script}</code>" if s.impact_script else ""),
    ("Icon", lambda s: _icon_cell(s.icon_resref)),
    ("Description", lambda s: s.description),
]


def link_spell_xrefs(spells: dict[str, "SpellRecord"],
                    id_maps: dict[str, dict[int, str]]) -> None:
    """Resolve Master + SubRadSpell{1..5} + FeatID references to human names.
    Keys consulted from `id_maps`: 'spell', 'feat'."""
    spell_id_to_name = id_maps.get("spell", {})
    feat_id_to_name = id_maps.get("feat", {})

    def _lookup(raw: str, table: dict[int, str]) -> str:
        try:
            return table.get(int(raw), "")
        except (ValueError, TypeError):
            return ""
    for sr in spells.values():
        sr.master_spell_name = _lookup(sr.master_spell, spell_id_to_name)
        sr.sub_radial_names = [_lookup(x, spell_id_to_name) for x in sr.sub_radial]
        sr.feat_id_name = _lookup(sr.feat_id, feat_id_to_name)


def load_spells(twoda_path, tlk: TlkResolver) -> tuple[dict[str, "SpellRecord"], dict[int, str]]:
    """Returns (`{label: SpellRecord}`, `{row_index: name}`).

    The id->name map covers EVERY row even if it isn't a "real" spell, because
    cross-references from other rows may still point at it.
    """
    with open(twoda_path) as f:
        tda = rollnw.TwoDA.from_string(f.read())
    out: dict[str, SpellRecord] = {}
    id_to_name: dict[int, str] = {}
    for r in range(tda.rows()):
        rec = SpellRecord.from_2da_row(tda, r, tlk)
        if rec.name:
            id_to_name[r] = rec.name
        if rec.is_real_spell():
            out[rec.label] = rec
    return out, id_to_name
