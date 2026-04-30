"""Typed class record extracted from classes.2da."""
from __future__ import annotations

from dataclasses import dataclass, field
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


# Per nwn.wiki's classes.2da page.
ALIGNMENT_BITS = [
    (0x01, "Lawful Good"), (0x02, "Lawful Neutral"), (0x04, "Lawful Evil"),
    (0x08, "Neutral Good"), (0x10, "True Neutral"), (0x20, "Neutral Evil"),
    (0x40, "Chaotic Good"), (0x80, "Chaotic Neutral"), (0x100, "Chaotic Evil"),
]
# AlignRstrctType flags; bits set in this column mean "the values in
# AlignRestrict apply to this axis".
ALIGN_AXIS_BITS = [
    (0x01, "Law/Chaos"), (0x02, "Good/Evil"),
]


def _decode_bitmask(value_str: str, bits: list[tuple[int, str]]) -> str:
    if not value_str:
        return ""
    try:
        v = int(value_str, 0)
    except ValueError:
        return value_str
    if v == 0:
        return "None"
    parts = [name for bit, name in bits if v & bit]
    return ", ".join(parts) if parts else f"(unknown: {value_str})"


# Recommended ability score columns -> nice display name.
ABILITY_COLS = [
    ("Str", "STR"), ("Dex", "DEX"), ("Con", "CON"),
    ("Wis", "WIS"), ("Int", "INT"), ("Cha", "CHA"),
]


@dataclass
class ClassRecord:
    label: str = ""
    name: str = ""
    name_strref: str = ""
    plural: str = ""
    plural_strref: str = ""
    description: str = ""
    description_strref: str = ""
    icon: str = ""
    hit_die: Optional[int] = None
    attack_bonus_table: str = ""
    feats_table: str = ""
    saving_throw_table: str = ""
    skills_table: str = ""
    bonus_feats_table: str = ""
    skill_point_base: Optional[int] = None
    spell_gain_table: str = ""
    spell_known_table: str = ""
    player_class: Optional[bool] = None
    spell_caster: Optional[bool] = None
    rec_abilities: dict[str, Optional[int]] = field(default_factory=dict)
    primary_ability: str = ""
    align_restrict_raw: str = ""
    align_restrict: str = ""
    align_axis_raw: str = ""
    align_axis: str = ""
    invert_restrict: Optional[bool] = None
    constant: str = ""
    pre_req_table: str = ""
    max_level: Optional[int] = None
    xp_penalty: Optional[bool] = None
    arc_spell_lvl_mod: Optional[int] = None
    div_spell_lvl_mod: Optional[int] = None
    epic_level: Optional[int] = None  # -1 = no epic; row of epic feats table otherwise

    @classmethod
    def from_2da_row(cls, tda: rollnw.TwoDA, row: int, tlk: TlkResolver) -> "ClassRecord":
        get = lambda c: _norm(tda.get_raw(row, tda.column_index(c)))
        gi = lambda c: _opt_int(tda.get_raw(row, tda.column_index(c)))

        align_raw = get("AlignRestrict")
        axis_raw = get("AlignRstrctType")

        rec_abilities: dict[str, Optional[int]] = {}
        for col, _ in ABILITY_COLS:
            rec_abilities[col] = gi(col)

        return cls(
            label=get("Label"),
            name=tlk.must_get(get("Name")) if get("Name") else "",
            name_strref=get("Name"),
            plural=tlk.must_get(get("Plural")) if get("Plural") else "",
            plural_strref=get("Plural"),
            description=tlk.must_get(get("Description")) if get("Description") else "",
            description_strref=get("Description"),
            icon=get("Icon"),
            hit_die=gi("HitDie"),
            attack_bonus_table=get("AttackBonusTable"),
            feats_table=get("FeatsTable"),
            saving_throw_table=get("SavingThrowTable"),
            skills_table=get("SkillsTable"),
            bonus_feats_table=get("BonusFeatsTable"),
            skill_point_base=gi("SkillPointBase"),
            spell_gain_table=get("SpellGainTable"),
            spell_known_table=get("SpellKnownTable"),
            player_class=_bool(get("PlayerClass")),
            spell_caster=_bool(get("SpellCaster")),
            rec_abilities=rec_abilities,
            primary_ability=get("PrimaryAbil"),
            align_restrict_raw=align_raw,
            align_restrict=_decode_bitmask(align_raw, ALIGNMENT_BITS),
            align_axis_raw=axis_raw,
            align_axis=_decode_bitmask(axis_raw, ALIGN_AXIS_BITS),
            invert_restrict=_bool(get("InvertRestrict")),
            constant=get("Constant"),
            pre_req_table=get("PreReqTable"),
            max_level=gi("MaxLevel"),
            xp_penalty=_bool(get("XPPenalty")),
            arc_spell_lvl_mod=gi("ArcSpellLvlMod"),
            div_spell_lvl_mod=gi("DivSpellLvlMod"),
            epic_level=gi("EpicLevel"),
        )

    def is_real_class(self) -> bool:
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

    def alignment_restriction(self) -> str:
        """Combine AlignRestrict + AlignRstrctType + InvertRestrict into a single
        readable cell. Empty string when there is no restriction."""
        if not self.align_restrict_raw or self.align_restrict_raw in ("0", "0x00"):
            return "None"
        verb = "Allowed only:" if self.invert_restrict else "Forbidden:"
        if self.align_axis:
            return f"{verb} {self.align_restrict} ({self.align_axis} axis)"
        return f"{verb} {self.align_restrict}"

    def recommended_abilities(self) -> str:
        """The 6 recommended ability scores from the class' default array."""
        parts = [f"{disp} {self.rec_abilities.get(col, '')}"
                 for col, disp in ABILITY_COLS
                 if self.rec_abilities.get(col) is not None]
        return ", ".join(parts) if parts else ""

    def epic_class(self) -> Optional[bool]:
        if self.epic_level is None:
            return None
        return self.epic_level >= 0

    def max_level_display(self) -> str:
        if self.max_level is None:
            return ""
        if self.max_level == 0:
            return "Unlimited"
        return str(self.max_level)


CLASS_DISPLAY_FIELDS: list[tuple[str, callable]] = [
    ("Name", lambda c: c.name),
    ("Plural", lambda c: c.plural),
    ("Player Class", lambda c: c.yes_no(c.player_class)),
    ("Spell Caster", lambda c: c.yes_no(c.spell_caster)),
    ("Hit Die", lambda c: "" if c.hit_die is None else f"d{c.hit_die}"),
    ("Skill Points / Level", lambda c: "" if c.skill_point_base is None else str(c.skill_point_base)),
    ("Primary Ability", lambda c: c.primary_ability),
    ("Recommended Ability Array", lambda c: c.recommended_abilities()),
    ("Alignment Restriction", lambda c: c.alignment_restriction()),
    ("Max Level", lambda c: c.max_level_display()),
    ("Multiclass XP Penalty", lambda c: c.yes_no(c.xp_penalty)),
    ("Arcane Spell Level Modifier", lambda c: "" if c.arc_spell_lvl_mod is None else str(c.arc_spell_lvl_mod)),
    ("Divine Spell Level Modifier", lambda c: "" if c.div_spell_lvl_mod is None else str(c.div_spell_lvl_mod)),
    ("Epic Class", lambda c: c.yes_no(c.epic_class())),
    ("Attack Bonus Table", lambda c: f"<code>{c.attack_bonus_table}</code>" if c.attack_bonus_table else ""),
    ("Saving Throw Table", lambda c: f"<code>{c.saving_throw_table}</code>" if c.saving_throw_table else ""),
    ("Feats Table", lambda c: f"<code>{c.feats_table}</code>" if c.feats_table else ""),
    ("Bonus Feats Table", lambda c: f"<code>{c.bonus_feats_table}</code>" if c.bonus_feats_table else ""),
    ("Skills Table", lambda c: f"<code>{c.skills_table}</code>" if c.skills_table else ""),
    ("Spell Gain Table", lambda c: f"<code>{c.spell_gain_table}</code>" if c.spell_gain_table else ""),
    ("Spell Known Table", lambda c: f"<code>{c.spell_known_table}</code>" if c.spell_known_table else ""),
    ("Prerequisite Table", lambda c: f"<code>{c.pre_req_table}</code>" if c.pre_req_table else ""),
    ("Script Constant", lambda c: f"<code>{c.constant}</code>" if c.constant else ""),
    ("Icon", lambda c: _icon_cell(c.icon)),
    ("Description", lambda c: c.description),
]


def load_classes(twoda_path, tlk: TlkResolver) -> tuple[dict[str, "ClassRecord"], dict[int, str]]:
    with open(twoda_path) as f:
        tda = rollnw.TwoDA.from_string(f.read())
    out: dict[str, ClassRecord] = {}
    id_to_name: dict[int, str] = {}
    for r in range(tda.rows()):
        rec = ClassRecord.from_2da_row(tda, r, tlk)
        if rec.name:
            id_to_name[r] = rec.name
        if rec.is_real_class():
            out[rec.label] = rec
    return out, id_to_name
