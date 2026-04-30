"""Per-content-type category derivation.

Each function takes a record and returns a list of MediaWiki category names
(no `Category:` prefix) to attach to its wiki page. Categories are emitted
as `[[Category:Name]]` tags inside the autosync block so they refresh
automatically on every sync; the wiki's Special:Categories index then acts
as the always-up-to-date browse-by-anything portal.

Naming conventions match what the human-curated pages already use on the
wiki, e.g. `NWN Bard Spells`, `NWN Wizard and Sorceror Spells` (note:
historical typo in the existing category name -- we mirror it rather than
splitting the bucket).
"""
from __future__ import annotations


# Display names for the Class column letters in spells.2da.
# Matches existing wiki categories. Note: NWN's `Wiz_Sorc` column lumps both
# wizards and sorcerers; the wiki's existing category is "Wizard and Sorceror"
# (with the historical "Sorceror" misspelling preserved for compatibility).
_SPELL_CLASS_DISPLAY = {
    "Bard": "Bard",
    "Cleric": "Cleric",
    "Druid": "Druid",
    "Paladin": "Paladin",
    "Ranger": "Ranger",
    "Wiz_Sorc": "Wizard and Sorceror",
    # Innate column means "creature/item power, not a learnable spell" -- skip.
}


def spell_categories(record) -> list[str]:
    """Categories for a spell page: NWN Spells + school + every class that
    can cast it (excluding Innate, which isn't player-castable)."""
    cats = ["NWN Spells"]
    if record.school:
        cats.append(f"NWN {record.school} Spells")
    for col, display in _SPELL_CLASS_DISPLAY.items():
        if record.class_levels.get(col) is not None:
            cats.append(f"NWN {display} Spells")
    return cats


def feat_categories(record) -> list[str]:
    """Categories for a feat page. We only emit signals we can derive cleanly
    from feat.2da; finer buckets like 'Fighter Bonus Feats' come from class
    bonus-feat tables we don't currently parse."""
    cats = ["NWN Feats"]
    if record.pre_req_epic:
        cats.append("NWN Epic Feats")
    return cats


def skill_categories(record) -> list[str]:
    return ["NWN Skills"]


def race_categories(record) -> list[str]:
    cats = ["NWN Races"]
    if record.player_race is True:
        cats.append("NWN Playable Races")
    return cats


def class_categories(record) -> list[str]:
    cats = ["NWN Classes"]
    if record.player_class is True:
        cats.append("NWN Playable Classes")
    if record.spell_caster is True:
        cats.append("NWN Spellcasting Classes")
    return cats


def masterfeat_categories(record) -> list[str]:
    return ["NWN Master Feats"]
