"""Typed feat record extracted from feat.2da, with field-level diff against stock."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import rollnw

from .tlk import TlkResolver
from .spell_record import _icon_cell  # shared helper -- icon resref -> wikitext cell


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


def _bool_field(v: Optional[str]) -> Optional[bool]:
    s = _norm(v)
    if not s:
        return None
    try:
        return bool(int(s))
    except ValueError:
        return None


# Per https://nwn.wiki/spaces/NWN1/pages/38175102/feat.2da
CATEGORY_NAMES = {
    "1": "Combat",
    "2": "Active Combat",
    "3": "Defensive",
    "4": "Magical",
    "5": "Class / Racial",
    "6": "Other",
}


def _format_uses_per_day(raw: str) -> str:
    """`****` -> unlimited, `-1` -> hardcoded, 100+ -> treated as unlimited."""
    if not raw:
        return "Unlimited / passive"
    try:
        n = int(raw)
    except ValueError:
        return raw
    if n == -1:
        return "Hardcoded (varies, e.g. by class level)"
    if n >= 100:
        return f"{n} (treated as unlimited)"
    return str(n)


@dataclass
class FeatRecord:
    label: str = ""
    name: str = ""
    name_strref: str = ""
    description: str = ""
    description_strref: str = ""
    icon: str = ""
    constant: str = ""

    # Prerequisites
    min_attack_bonus: Optional[int] = None
    min_str: Optional[int] = None
    min_dex: Optional[int] = None
    min_int: Optional[int] = None
    min_wis: Optional[int] = None
    min_con: Optional[int] = None
    min_cha: Optional[int] = None
    min_spell_level: Optional[int] = None
    prereq_feat_1: str = ""
    prereq_feat_2: str = ""
    or_req_feats: list[str] = field(default_factory=list)
    req_skill: str = ""
    req_skill_min: Optional[int] = None
    req_skill_2: str = ""
    req_skill_min_2: Optional[int] = None
    min_level: Optional[int] = None
    min_level_class: Optional[int] = None
    max_level: Optional[int] = None
    min_fort_save: Optional[int] = None
    pre_req_epic: Optional[bool] = None

    # Behavior
    gain_multiple: Optional[bool] = None
    effects_stack: Optional[bool] = None
    all_classes_can_use: Optional[bool] = None
    target_self: Optional[bool] = None
    uses_per_day: str = ""
    spell_id: str = ""
    successor: str = ""
    master_feat: str = ""
    category: str = ""
    category_raw: str = ""
    hostile: Optional[bool] = None
    req_action: Optional[bool] = None

    # Resolved cross-references (filled in by link_xrefs after loading both 2das).
    prereq_feat_1_name: str = ""
    prereq_feat_2_name: str = ""
    or_req_feat_names: list[str] = field(default_factory=list)
    successor_name: str = ""
    master_feat_name: str = ""
    spell_id_name: str = ""

    @classmethod
    def from_2da_row(cls, tda: rollnw.TwoDA, row: int, tlk: TlkResolver) -> "FeatRecord":
        get = lambda c: _norm(tda.get_raw(row, tda.column_index(c)))
        gi = lambda c: _opt_int(tda.get_raw(row, tda.column_index(c)))
        gb = lambda c: _bool_field(tda.get_raw(row, tda.column_index(c)))

        or_feats = []
        for col in ("OrReqFeat0", "OrReqFeat1", "OrReqFeat2", "OrReqFeat3", "OrReqFeat4"):
            v = get(col)
            if v:
                or_feats.append(v)

        category_raw = get("CATEGORY")
        return cls(
            label=get("LABEL"),
            name=tlk.must_get(get("FEAT")) if get("FEAT") else "",
            name_strref=get("FEAT"),
            description=tlk.must_get(get("DESCRIPTION")) if get("DESCRIPTION") else "",
            description_strref=get("DESCRIPTION"),
            icon=get("ICON"),
            constant=get("Constant"),
            min_attack_bonus=gi("MINATTACKBONUS"),
            min_str=gi("MINSTR"),
            min_dex=gi("MINDEX"),
            min_int=gi("MININT"),
            min_wis=gi("MINWIS"),
            min_con=gi("MINCON"),
            min_cha=gi("MINCHA"),
            min_spell_level=gi("MINSPELLLVL"),
            prereq_feat_1=get("PREREQFEAT1"),
            prereq_feat_2=get("PREREQFEAT2"),
            or_req_feats=or_feats,
            req_skill=get("REQSKILL"),
            req_skill_min=gi("ReqSkillMinRanks"),
            req_skill_2=get("REQSKILL2"),
            req_skill_min_2=gi("ReqSkillMinRanks2"),
            min_level=gi("MinLevel"),
            min_level_class=gi("MinLevelClass"),
            max_level=gi("MaxLevel"),
            min_fort_save=gi("MinFortSave"),
            pre_req_epic=gb("PreReqEpic"),
            gain_multiple=gb("GAINMULTIPLE"),
            effects_stack=gb("EFFECTSSTACK"),
            all_classes_can_use=gb("ALLCLASSESCANUSE"),
            target_self=gb("TARGETSELF"),
            uses_per_day=get("USESPERDAY"),
            spell_id=get("SPELLID"),
            successor=get("SUCCESSOR"),
            master_feat=get("MASTERFEAT"),
            category=CATEGORY_NAMES.get(category_raw, category_raw),
            category_raw=category_raw,
            hostile=gb("HostileFeat"),
            req_action=gb("ReqAction"),
        )

    def is_real_feat(self) -> bool:
        if not self.label:
            return False
        if self.label.startswith(("DEL_", "PADDING_", "Reserved_", "DELETED_")):
            return False
        if not self.name:
            return False
        return True

    # --- public-facing fields ---

    def ability_prereqs(self) -> str:
        parts = []
        for label, val in [
            ("STR", self.min_str), ("DEX", self.min_dex), ("CON", self.min_con),
            ("INT", self.min_int), ("WIS", self.min_wis), ("CHA", self.min_cha),
        ]:
            if val is not None:
                parts.append(f"{label} {val}")
        return ", ".join(parts) if parts else ""

    def feat_prereqs(self) -> str:
        def _link(name: str, raw: str) -> str:
            if name:
                return f"[[{name}]]"
            return f"<code>feat#{raw}</code>"
        parts = []
        if self.prereq_feat_1:
            parts.append(_link(self.prereq_feat_1_name, self.prereq_feat_1))
        if self.prereq_feat_2:
            parts.append(_link(self.prereq_feat_2_name, self.prereq_feat_2))
        if self.or_req_feats:
            ors = []
            for raw, name in zip(self.or_req_feats,
                                 self.or_req_feat_names + [""] * len(self.or_req_feats)):
                ors.append(_link(name, raw))
            parts.append("any of: " + ", ".join(ors))
        return "; ".join(parts) if parts else ""

    def skill_prereqs(self) -> str:
        parts = []
        if self.req_skill and self.req_skill_min is not None:
            parts.append(f"skill#{self.req_skill} {self.req_skill_min} ranks")
        if self.req_skill_2 and self.req_skill_min_2 is not None:
            parts.append(f"skill#{self.req_skill_2} {self.req_skill_min_2} ranks")
        return "; ".join(parts) if parts else ""

    def level_prereqs(self) -> str:
        parts = []
        if self.min_level is not None:
            parts.append(f"min char level {self.min_level}")
        if self.min_level_class is not None:
            parts.append(f"min class level {self.min_level_class}")
        if self.max_level is not None:
            parts.append(f"max char level {self.max_level}")
        if self.min_fort_save is not None:
            parts.append(f"min Fort save {self.min_fort_save}")
        if self.pre_req_epic:
            parts.append("epic")
        if self.min_attack_bonus is not None:
            parts.append(f"min BAB {self.min_attack_bonus}")
        if self.min_spell_level is not None:
            parts.append(f"min spell level {self.min_spell_level}")
        return "; ".join(parts) if parts else ""

    def yes_no(self, b: Optional[bool]) -> str:
        if b is None:
            return ""
        return "Yes" if b else "No"


def _xref(name: str, kind: str, raw: str) -> str:
    if name:
        return f"[[{name}]]"
    if not raw:
        return ""
    return f"<code>{kind}#{raw}</code>"


FEAT_DISPLAY_FIELDS: list[tuple[str, callable]] = [
    ("Name", lambda f: f.name),
    ("Category", lambda f: f.category),
    ("Ability Prerequisites", lambda f: f.ability_prereqs()),
    ("Feat Prerequisites", lambda f: f.feat_prereqs()),
    ("Skill Prerequisites", lambda f: f.skill_prereqs()),
    ("Level / Other Prerequisites", lambda f: f.level_prereqs()),
    ("Uses per Day", lambda f: _format_uses_per_day(f.uses_per_day)),
    ("Target Self", lambda f: f.yes_no(f.target_self)),
    ("All Classes Can Use", lambda f: f.yes_no(f.all_classes_can_use)),
    ("Gain Multiple Times", lambda f: f.yes_no(f.gain_multiple)),
    ("Effects Stack", lambda f: f.yes_no(f.effects_stack)),
    ("Hostile", lambda f: f.yes_no(f.hostile)),
    ("Uses Action Queue", lambda f: f.yes_no(f.req_action)),
    ("Successor Feat", lambda f: _xref(f.successor_name, "feat", f.successor)),
    ("Master Feat", lambda f: _xref(f.master_feat_name, "masterfeat", f.master_feat)),
    ("Spell Trigger", lambda f: _xref(f.spell_id_name, "spell", f.spell_id)),
    ("Script Constant", lambda f: f"<code>{f.constant}</code>" if f.constant else ""),
    ("Icon", lambda f: _icon_cell(f.icon)),
    ("Description", lambda f: f.description),
]


def link_feat_xrefs(feats: dict[str, "FeatRecord"],
                    id_maps: dict[str, dict[int, str]]) -> None:
    """Resolve PREREQFEAT / OrReqFeat / SUCCESSOR / MASTERFEAT / SPELLID
    references on every feat record into human-readable names. Keys consulted
    from `id_maps`: 'feat', 'spell', 'masterfeat'."""
    feat_id_to_name = id_maps.get("feat", {})
    spell_id_to_name = id_maps.get("spell", {})
    masterfeat_id_to_name = id_maps.get("masterfeat", {})

    def _lookup(table: dict[int, str], raw: str) -> str:
        try:
            return table.get(int(raw), "")
        except (ValueError, TypeError):
            return ""
    for fr in feats.values():
        fr.prereq_feat_1_name = _lookup(feat_id_to_name, fr.prereq_feat_1)
        fr.prereq_feat_2_name = _lookup(feat_id_to_name, fr.prereq_feat_2)
        fr.or_req_feat_names = [_lookup(feat_id_to_name, x) for x in fr.or_req_feats]
        fr.successor_name = _lookup(feat_id_to_name, fr.successor)
        fr.master_feat_name = _lookup(masterfeat_id_to_name, fr.master_feat)
        fr.spell_id_name = _lookup(spell_id_to_name, fr.spell_id)


def load_feats(twoda_path, tlk: TlkResolver) -> tuple[dict[str, "FeatRecord"], dict[int, str]]:
    """Returns (`{label: FeatRecord}`, `{row_index: name}`).

    The id->name map covers EVERY row (even placeholder/deleted ones), because
    cross-references from other feats may still point at them.
    """
    with open(twoda_path) as f:
        tda = rollnw.TwoDA.from_string(f.read())
    out: dict[str, FeatRecord] = {}
    id_to_name: dict[int, str] = {}
    for r in range(tda.rows()):
        rec = FeatRecord.from_2da_row(tda, r, tlk)
        if rec.name:
            id_to_name[r] = rec.name
        if rec.is_real_feat():
            out[rec.label] = rec
    return out, id_to_name
