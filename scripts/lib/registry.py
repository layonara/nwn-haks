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

from .spell_record import (
    SPELL_DISPLAY_FIELDS, load_spells, link_spell_xrefs,
)
from .feat_record import (
    FEAT_DISPLAY_FIELDS, load_feats, link_feat_xrefs,
)
from .skill_record import SKILL_DISPLAY_FIELDS, load_skills
from .race_record import RACE_DISPLAY_FIELDS, load_races, link_race_xrefs
from .class_record import CLASS_DISPLAY_FIELDS, load_classes
from .masterfeat_record import (
    MASTERFEAT_DISPLAY_FIELDS, load_masterfeats_full,
    link_masterfeat_variants, extra_render_masterfeat,
)
from .categories import (
    spell_categories, feat_categories, skill_categories, race_categories,
    class_categories, masterfeat_categories,
)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# disambig_priority: lowest wins the bare title in cross-kind collisions.
# Spells take the bare title because they're the most-linked-to / most-iconic
# content type and almost every wiki cross-reference assumes "Heal" means the
# spell. Skill is next (also commonly bare-linked). Race/Class only collide
# with each other on creature-type names where the "race" perspective wins
# because that's the page players land on. Feat is last because feat names
# overwhelmingly piggyback on the spell or skill they cast.
CONTENT_TYPES: list[ContentType] = [
    ContentType(
        kind="spell",
        template_name="NWN:Spell",
        layo_2da=REPO_ROOT / "config/2da/spells.2da",
        stock_2da=REPO_ROOT / "vendor/stock/spells.2da",
        display_fields=SPELL_DISPLAY_FIELDS,
        loader=load_spells,
        xref_link=link_spell_xrefs,
        categories=spell_categories,
        icon_attr="icon_resref",
        tlk_columns=("Name", "SpellDesc", "AltMessage"),
        disambig_suffix="Spell",
        disambig_priority=0,
    ),
    ContentType(
        kind="skill",
        template_name="NWN:Skill",
        layo_2da=REPO_ROOT / "config/2da/skills.2da",
        stock_2da=REPO_ROOT / "vendor/stock/skills.2da",
        display_fields=SKILL_DISPLAY_FIELDS,
        loader=load_skills,
        xref_link=None,
        categories=skill_categories,
        icon_attr="icon",
        tlk_columns=("Name", "Description"),
        disambig_suffix="Skill",
        disambig_priority=1,
    ),
    ContentType(
        kind="race",
        template_name="NWN:Race",
        layo_2da=REPO_ROOT / "config/2da/racialtypes.2da",
        stock_2da=REPO_ROOT / "vendor/stock/racialtypes.2da",
        display_fields=RACE_DISPLAY_FIELDS,
        loader=load_races,
        xref_link=link_race_xrefs,
        categories=race_categories,
        icon_attr="icon",
        tlk_columns=("Name", "ConverName", "ConverNameLower", "NamePlural",
                     "Description", "Biography"),
        disambig_suffix="Race",
        disambig_priority=2,
    ),
    ContentType(
        kind="class",
        template_name="NWN:Class",
        layo_2da=REPO_ROOT / "config/2da/classes.2da",
        stock_2da=REPO_ROOT / "vendor/stock/classes.2da",
        display_fields=CLASS_DISPLAY_FIELDS,
        loader=load_classes,
        xref_link=None,
        categories=class_categories,
        icon_attr="icon",
        tlk_columns=("Name", "Plural", "Lower", "Description"),
        disambig_suffix="Class",
        disambig_priority=3,
    ),
    ContentType(
        kind="feat",
        template_name="NWN:Feat",
        layo_2da=REPO_ROOT / "config/2da/feat.2da",
        stock_2da=REPO_ROOT / "vendor/stock/feat.2da",
        display_fields=FEAT_DISPLAY_FIELDS,
        loader=load_feats,
        xref_link=link_feat_xrefs,
        categories=feat_categories,
        icon_attr="icon",
        tlk_columns=("FEAT", "DESCRIPTION"),
        disambig_suffix="Feat",
        disambig_priority=4,
    ),
    # Master feats are navigation hubs that list all their child feat
    # variants. They use `post_link` (rather than `xref_link`) so they can
    # see the FULLY-RESOLVED page titles of every child feat -- including
    # any cross-kind disambig suffixes -- and emit working wiki links via
    # the `extra_render` hook.
    ContentType(
        kind="masterfeat",
        template_name="NWN:Masterfeat",
        layo_2da=REPO_ROOT / "config/2da/masterfeats.2da",
        stock_2da=REPO_ROOT / "vendor/stock/masterfeats.2da",
        display_fields=MASTERFEAT_DISPLAY_FIELDS,
        loader=load_masterfeats_full,
        post_link=link_masterfeat_variants,
        extra_render=extra_render_masterfeat,
        categories=masterfeat_categories,
        # Suppress orphan master feats (rows in masterfeats.2da with zero
        # feats pointing at them via the MASTERFEAT column). Such rows are
        # almost always abandoned plans (e.g. LayonaraEpicSpells, row 18)
        # and rendering a page for them produces an empty Variants section
        # plus a misleading description that's easy to mistake for a real
        # master feat hub.
        skip_when=lambda r: not r.variants,
        icon_attr="icon",
        tlk_columns=("STRREF", "DESCRIPTION"),
        # Master feats win the bare title (no suffix) when no other kind
        # claims it. The disambig_priority is high so that on the rare
        # occasion a master-feat name DID collide with e.g. a spell, the
        # spell wins the bare title (matching player intuition).
        disambig_suffix="Master Feat",
        disambig_priority=5,
    ),
]


# Side tables -- loaded for xref name resolution but not synced to the wiki.
# Each entry: (kind_id_for_id_maps, layo_path, loader). Currently empty;
# every aux table has been promoted to a full ContentType.
AUX_LOADERS: list[tuple[str, Path, callable]] = []


def get_template_names() -> tuple[str, ...]:
    """All template names so splice_into_page can detect any of them on a page."""
    return tuple(ct.template_name for ct in CONTENT_TYPES)
