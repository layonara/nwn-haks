"""Registry of all wiki-synced 2da content types for Layonara.

To add a new content type:

  1. Write `lib/<thing>_record.py` exposing:
       <THING>_DISPLAY_FIELDS  -- list[(label, getter)]
       load_<things>(twoda_path, tlk) -> (records, id_to_name)
       link_<thing>_xrefs(records, id_maps)   # optional
  2. Add a ContentType entry to CONTENT_TYPES below.
  3. Optionally create the matching `Template:NWN:<Thing>` on the wiki
     (mirroring `Template:NWN:Spell`) so newly-created pages render their
     `desc=` parameter cleanly above the autosync block.

The wiki_sync orchestrator is registry-driven: it loops over CONTENT_TYPES
and AUX_LOADERS without any per-type special-cases.
"""
from __future__ import annotations

from pathlib import Path

from .content_type import ContentType

# Loader-only side tables (not first-class wiki-page content; just lookup
# tables for cross-references). Each entry is (kind, layo_path, stock_path,
# loader). Loader signature is `loader(path, tlk) -> {row: name}`.
from .masterfeats import load_masterfeats
from .spell_record import (
    SPELL_DISPLAY_FIELDS, load_spells, link_spell_xrefs,
)
from .feat_record import (
    FEAT_DISPLAY_FIELDS, load_feats, link_feat_xrefs,
)
from .skill_record import SKILL_DISPLAY_FIELDS, load_skills
from .race_record import RACE_DISPLAY_FIELDS, load_races, link_race_xrefs
from .class_record import CLASS_DISPLAY_FIELDS, load_classes


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


CONTENT_TYPES: list[ContentType] = [
    ContentType(
        kind="spell",
        template_name="NWN:Spell",
        layo_2da=REPO_ROOT / "config/2da/spells.2da",
        stock_2da=REPO_ROOT / "vendor/stock/spells.2da",
        display_fields=SPELL_DISPLAY_FIELDS,
        loader=load_spells,
        xref_link=link_spell_xrefs,
        icon_attr="icon_resref",
        tlk_columns=("Name", "SpellDesc", "AltMessage"),
    ),
    ContentType(
        kind="feat",
        template_name="NWN:Feat",
        layo_2da=REPO_ROOT / "config/2da/feat.2da",
        stock_2da=REPO_ROOT / "vendor/stock/feat.2da",
        display_fields=FEAT_DISPLAY_FIELDS,
        loader=load_feats,
        xref_link=link_feat_xrefs,
        icon_attr="icon",
        tlk_columns=("FEAT", "DESCRIPTION"),
    ),
    ContentType(
        kind="class",
        template_name="NWN:Class",
        layo_2da=REPO_ROOT / "config/2da/classes.2da",
        stock_2da=REPO_ROOT / "vendor/stock/classes.2da",
        display_fields=CLASS_DISPLAY_FIELDS,
        loader=load_classes,
        xref_link=None,
        icon_attr="icon",
        tlk_columns=("Name", "Plural", "Lower", "Description"),
    ),
    ContentType(
        kind="race",
        template_name="NWN:Race",
        layo_2da=REPO_ROOT / "config/2da/racialtypes.2da",
        stock_2da=REPO_ROOT / "vendor/stock/racialtypes.2da",
        display_fields=RACE_DISPLAY_FIELDS,
        loader=load_races,
        xref_link=link_race_xrefs,
        icon_attr="icon",
        tlk_columns=("Name", "ConverName", "ConverNameLower", "NamePlural",
                     "Description", "Biography"),
    ),
    ContentType(
        kind="skill",
        template_name="NWN:Skill",
        layo_2da=REPO_ROOT / "config/2da/skills.2da",
        stock_2da=REPO_ROOT / "vendor/stock/skills.2da",
        display_fields=SKILL_DISPLAY_FIELDS,
        loader=load_skills,
        xref_link=None,
        icon_attr="icon",
        tlk_columns=("Name", "Description"),
    ),
]


# Side tables -- loaded for xref name resolution but not synced to the wiki.
# Each entry: (kind_id_for_id_maps, layo_path, loader)
# Stock counterpart is also looked up if it exists.
AUX_LOADERS: list[tuple[str, Path, callable]] = [
    ("masterfeat", REPO_ROOT / "config/2da/masterfeats.2da", load_masterfeats),
]


def get_template_names() -> tuple[str, ...]:
    """All template names so splice_into_page can detect any of them on a page."""
    return tuple(ct.template_name for ct in CONTENT_TYPES)
