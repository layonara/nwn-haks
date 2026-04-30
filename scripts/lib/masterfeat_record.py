"""Typed master-feat record extracted from masterfeats.2da.

Master feats are containers for weapon-/spell-/skill-specific feat variants:
e.g. `WeaponFocus` (master) -> `Weapon Focus (longsword)`, `Weapon Focus
(rapier)`, etc. (variants). The wiki page acts as a navigation hub linking
to all variants and surfacing any Layonara-vs-stock variant-set drift
(e.g. Layonara adds `Devastating Critical (katar)` that stock NWN:EE doesn't
have).

We deliberately keep the in-table fields minimal (Name, Icon, Variant Count,
Description) and render the variant bullet list as a separate `== Variants ==`
section via the `extra_render` hook so it lands as proper wiki structure
rather than a cramped table cell.
"""
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


@dataclass
class MasterFeatRecord:
    label: str = ""
    name: str = ""
    name_strref: str = ""
    description: str = ""
    description_strref: str = ""
    icon: str = ""

    # Filled in by `link_masterfeat_variants` after both feat/masterfeat
    # records have loaded AND the cross-kind disambiguator has computed
    # variant page titles. Each entry is (variant_label, variant_name,
    # variant_page_title), sorted by variant_name (case-insensitive).
    variants: list[tuple[str, str, str]] = field(default_factory=list)

    @classmethod
    def from_2da_row(cls, tda: rollnw.TwoDA, row: int, tlk: TlkResolver) -> "MasterFeatRecord":
        get = lambda c: _norm(tda.get_raw(row, tda.column_index(c)))
        name_ref = get("STRREF")
        desc_ref = get("DESCRIPTION")
        return cls(
            label=get("LABEL"),
            name=tlk.must_get(name_ref) if name_ref else "",
            name_strref=name_ref,
            description=tlk.must_get(desc_ref) if desc_ref else "",
            description_strref=desc_ref,
            icon=get("ICON"),
        )

    def is_real(self) -> bool:
        return bool(self.label) and bool(self.name)


def _format_variants_summary(rec: "MasterFeatRecord") -> str:
    """Compact one-liner for the stat table; the full list is rendered below."""
    if not rec.variants:
        return "''(no variants found in feat.2da)''"
    n = len(rec.variants)
    return f"{n} variant" + ("s" if n != 1 else "")


MASTERFEAT_DISPLAY_FIELDS: list[tuple[str, callable]] = [
    ("Name", lambda f: f.name),
    ("Icon", lambda f: _icon_cell(f.icon)),
    ("Variant Count", _format_variants_summary),
    ("Description", lambda f: f.description),
]


def load_masterfeats_full(twoda_path, tlk: TlkResolver):
    """Returns (`{label: MasterFeatRecord}`, `{row_index: name}`).

    `id_to_name` covers all rows so that feat.2da's `MASTERFEAT` cross-refs
    still resolve correctly via the registry's id_maps (this used to be the
    sole purpose of the now-retired aux loader in `lib/masterfeats.py`).
    """
    with open(twoda_path) as f:
        tda = rollnw.TwoDA.from_string(f.read())
    out: dict[str, MasterFeatRecord] = {}
    id_to_name: dict[int, str] = {}
    for r in range(tda.rows()):
        rec = MasterFeatRecord.from_2da_row(tda, r, tlk)
        if rec.name:
            id_to_name[r] = rec.name
        if rec.is_real():
            out[rec.label] = rec
    return out, id_to_name


def _populate_variants(masters: dict[str, "MasterFeatRecord"],
                       feat_records,  # dict[str, FeatRecord]
                       cross_kind_suffixes: dict[tuple[str, str], str]) -> None:
    """Bucket every feat that names this master feat under its label."""
    name_to_master_label: dict[str, str] = {m.name: lab for lab, m in masters.items()}
    bucket: dict[str, list[tuple[str, object]]] = {}
    for vlabel, vrec in feat_records.items():
        mname = vrec.master_feat_name
        if not mname:
            continue
        mlabel = name_to_master_label.get(mname)
        if not mlabel:
            continue
        bucket.setdefault(mlabel, []).append((vlabel, vrec))
    for mlabel, mrec in masters.items():
        triples = []
        for vlabel, vrec in bucket.get(mlabel, []):
            suffix = cross_kind_suffixes.get(("feat", vlabel), "")
            title = f"{vrec.name} ({suffix})" if suffix else vrec.name
            triples.append((vlabel, vrec.name, title))
        triples.sort(key=lambda t: t[1].lower())
        mrec.variants = triples


def link_masterfeat_variants(layo_records: dict[str, "MasterFeatRecord"],
                             stock_records: dict[str, "MasterFeatRecord"],
                             all_records: dict[str, tuple[dict, dict]],
                             layo_id_maps: dict[str, dict[int, str]],
                             stock_id_maps: dict[str, dict[int, str]],
                             cross_kind_suffixes: dict[tuple[str, str], str],
                             ) -> None:
    """ContentType.post_link hook.

    Runs AFTER every kind's xref_link AND the cross-kind disambiguator have
    finished, so the variant page titles we emit here are the same titles
    the main loop will write the variant pages to. That's what makes the
    `[[Weapon Focus (longsword)]]` links on the master-feat hub page
    actually resolve.
    """
    feat_layo, feat_stock = all_records.get("feat", ({}, {}))
    _populate_variants(layo_records, feat_layo, cross_kind_suffixes)
    _populate_variants(stock_records, feat_stock, cross_kind_suffixes)
    # Suppress unused-arg lint (kept in signature for symmetry with future hooks).
    del layo_id_maps, stock_id_maps


def extra_render_masterfeat(layo: "MasterFeatRecord",
                            stock: Optional["MasterFeatRecord"]) -> str:
    """ContentType.extra_render hook -- the `== Variants ==` section.

    Renders the full Layonara variant list as a bullet list. When the Layonara
    variant set diverges from stock, two short notes ahead of the list call
    out additions/removals.

    Diffing is done by *page title*, not by 2da label, because Layonara
    sometimes renames a label (e.g. stock `FEAT_WEAPON_FOCUS_TRIDENT` ->
    layo `WeapFocTrident`) while keeping the same player-facing name. Those
    cases must NOT show up as "removed in Layonara".
    """
    layo_titles = sorted({t for _, _, t in layo.variants})
    stock_titles: set[str] = set()
    if stock is not None:
        stock_titles = {t for _, _, t in stock.variants}

    layo_only_titles = sorted(set(layo_titles) - stock_titles)
    stock_only_titles = sorted(stock_titles - set(layo_titles))

    lines: list[str] = ["", "== Variants =="]

    # When this master feat has no stock counterpart at all, every variant is
    # by definition Layonara-only -- the bullet list below already shows them
    # so the additions line is redundant noise. Only surface diff lines when
    # there's an actual stock baseline to compare against.
    if stock is None:
        layo_only_titles = []

    if layo_only_titles or stock_only_titles:
        if layo_only_titles:
            n = len(layo_only_titles)
            lines.append(
                f"''Layonara adds {n} variant"
                + ("s " if n != 1 else " ")
                + "not in stock NWN:EE: ''"
                + ", ".join(f"[[{t}]]" for t in layo_only_titles)
            )
        if stock_only_titles:
            n = len(stock_only_titles)
            removed_names = ", ".join(f"<code>{t}</code>"
                                      for t in stock_only_titles)
            lines.append(
                f"''Stock NWN:EE has {n} variant"
                + ("s " if n != 1 else " ")
                + "removed in Layonara: ''"
                + removed_names
            )
        lines.append("")

    if not layo.variants:
        lines.append("''(none -- no feat in feat.2da references this master feat.)''")
    else:
        for _, _, title in layo.variants:
            lines.append(f"* [[{title}]]")

    lines.append("")
    return "\n".join(lines)
