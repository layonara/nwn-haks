"""Typed skill record extracted from skills.2da, with field-level diff against stock."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import rollnw

from .tlk import TlkResolver
from .spell_record import _icon_cell  # shared helper

KEY_ABILITY_NAMES = {
    "STR": "Strength",
    "DEX": "Dexterity",
    "CON": "Constitution",
    "INT": "Intelligence",
    "WIS": "Wisdom",
    "CHA": "Charisma",
}


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


@dataclass
class SkillRecord:
    label: str = ""
    name: str = ""
    name_strref: str = ""
    description: str = ""
    description_strref: str = ""
    icon: str = ""
    untrained: Optional[bool] = None
    key_ability_raw: str = ""
    key_ability: str = ""
    armor_check_penalty: Optional[bool] = None
    all_classes_can_use: Optional[bool] = None
    max_cr: str = ""
    constant: str = ""
    hostile: Optional[bool] = None

    @classmethod
    def from_2da_row(cls, tda: rollnw.TwoDA, row: int, tlk: TlkResolver) -> "SkillRecord":
        get = lambda c: _norm(tda.get_raw(row, tda.column_index(c)))
        key = get("KeyAbility").upper()
        return cls(
            label=get("Label"),
            name=tlk.must_get(get("Name")) if get("Name") else "",
            name_strref=get("Name"),
            description=tlk.must_get(get("Description")) if get("Description") else "",
            description_strref=get("Description"),
            icon=get("Icon"),
            untrained=_bool(get("Untrained")),
            key_ability_raw=key,
            key_ability=KEY_ABILITY_NAMES.get(key, key),
            armor_check_penalty=_bool(get("ArmorCheckPenalty")),
            all_classes_can_use=_bool(get("AllClassesCanUse")),
            max_cr=get("MaxCR"),
            constant=get("Constant"),
            hostile=_bool(get("HostileSkill")),
        )

    def is_real_skill(self) -> bool:
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


SKILL_DISPLAY_FIELDS: list[tuple[str, callable]] = [
    ("Name", lambda s: s.name),
    ("Key Ability", lambda s: s.key_ability),
    ("Usable Untrained", lambda s: s.yes_no(s.untrained)),
    ("All Classes Can Use", lambda s: s.yes_no(s.all_classes_can_use)),
    ("Armor Check Penalty Applies", lambda s: s.yes_no(s.armor_check_penalty)),
    ("Hostile Skill", lambda s: s.yes_no(s.hostile)),
    ("Max CR", lambda s: s.max_cr),
    ("Script Constant", lambda s: f"<code>{s.constant}</code>" if s.constant else ""),
    ("Icon", lambda s: _icon_cell(s.icon)),
    ("Description", lambda s: s.description),
]


def load_skills(twoda_path, tlk: TlkResolver) -> tuple[dict[str, "SkillRecord"], dict[int, str]]:
    """Returns (`{label: SkillRecord}`, `{row_index: name}`)."""
    with open(twoda_path) as f:
        tda = rollnw.TwoDA.from_string(f.read())
    out: dict[str, SkillRecord] = {}
    id_to_name: dict[int, str] = {}
    for r in range(tda.rows()):
        rec = SkillRecord.from_2da_row(tda, r, tlk)
        if rec.name:
            id_to_name[r] = rec.name
        if rec.is_real_skill():
            out[rec.label] = rec
    return out, id_to_name
