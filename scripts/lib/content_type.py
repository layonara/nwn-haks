"""Declarative registry of "things we sync to the wiki from a 2da".

Adding a new content type is a matter of writing one record dataclass +
display-fields list + loader, then appending a `ContentType` entry below.
The wiki_sync orchestrator does the rest -- no special-cases per type.

A ContentType describes:

  kind:           short id ("spell", "feat", "class")
  template_name:  MediaWiki template invocation name (`{{<template_name>}}`)
  layo_2da:       path to the Layonara overrides 2da
  stock_2da:      path to the vendored stock 2da (None => no stock comparison)
  display_fields: list of (label, getter) used by render.py
  loader:         callable(twoda_path, tlk) -> (records_dict, id_to_name_dict)
                  returning {label: record} and a row_index->name map for xrefs
  xref_link:      optional callable(layo_records, stock_records, all_id_maps)
                  invoked once both sides are loaded so records can resolve
                  cross-2da numeric ids into human-readable names
  post_link:      optional callable(layo_records, stock_records, all_records,
                                    layo_id_maps, stock_id_maps,
                                    cross_kind_suffixes)
                  invoked AFTER `xref_link` for every kind has run AND the
                  cross-kind disambiguator is computed. Use this when a kind
                  needs visibility into other kinds' resolved records (e.g.
                  master feats inventorying their child feat variants and
                  resolving their wiki page titles).
  extra_render:   optional callable(layo_record, stock_record_or_none) -> str
                  Wikitext appended inside the autosync block, after the
                  comparison/identical/custom table and before the source
                  attribution note. Use for content that doesn't fit a
                  per-field row (e.g. a `== Variants ==` bullet list).
  categories:     optional callable(layo_record) -> list[str]
                  MediaWiki category names (no `Category:` prefix) to attach
                  to the page. Emitted as `[[Category:Name]]` tags inside the
                  autosync block so they refresh on every sync. Lets the wiki
                  Special:Categories index automatically reflect the registry
                  without us having to maintain a separate index page.
  icon_attr:      attribute name on each record that holds the icon resref
                  (None => no icon row in the autosync table)
  tlk_columns:    columns whose values are TLK string references; the stock
                  baseline extractor uses these to build a filtered TLK subset

  disambig_suffix:    short label used when a page-title collision with another
                      kind forces a suffix (e.g. "Skill" -> "Heal (Skill)").
                      Empty string means "this kind wins the bare title".
                      Conflicts where multiple kinds want the bare title are
                      resolved by `disambig_priority` (lowest wins).
  disambig_priority:  smaller = wins the bare title in cross-kind collisions.
                      Default order: spell(0) > skill(1) > race(2) > class(3) >
                      feat(4). Tweak only if you need to override which kind
                      keeps the canonical name.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


@dataclass
class ContentType:
    kind: str
    template_name: str
    layo_2da: Path
    stock_2da: Optional[Path]
    display_fields: list[tuple[str, Callable]]
    loader: Callable
    xref_link: Optional[Callable] = None
    post_link: Optional[Callable] = None
    extra_render: Optional[Callable] = None
    categories: Optional[Callable] = None
    icon_attr: Optional[str] = None
    tlk_columns: tuple[str, ...] = field(default_factory=tuple)
    disambig_suffix: str = ""
    disambig_priority: int = 100

    def get_icon(self, record) -> str:
        """Return the icon resref for `record`, or empty string."""
        if not self.icon_attr:
            return ""
        return getattr(record, self.icon_attr, "") or ""
