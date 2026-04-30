#!/usr/bin/env python3
"""Create stub description pages for every Category:* the wiki sync emits.

MediaWiki renders `[[:Category:Foo]]` as a red link when the category's
description page (the one at the URL `/wiki/Category:Foo`) has never had
wikitext written to it -- regardless of whether the category has hundreds
of members. Most of the NWN reference categories (NWN Feats, NWN Master
Feats, NWN Epic Feats, NWN Skills, etc.) are in that state because we
populate them implicitly via the sync, never via a description-page edit.

This is a one-shot bootstrap: walk every record in the registry, collect
the union of categories the sync would emit, query the wiki for which of
those don't yet have a description page, and create stubs for those.

Run with the same env as wiki_sync.py:

    WIKI_CONTAINER=<coolify-container-id> WIKI_BOT_USER=Orth \\
        python3 scripts/bootstrap_category_pages.py [--dry-run]

Idempotent. Re-running only creates pages for categories that didn't
exist on the previous run -- safe to re-invoke after adding new content
types or category buckets.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import os

from lib.registry import CONTENT_TYPES
from lib.tlk import TlkResolver
from lib.wiki_client import WikiClient, WikiCreds, make_default_backend


# One-line description per category. Anything not in this map gets a
# generic fallback `Auto-populated index of NWN <kind>.`
DESCRIPTIONS = {
    "NWN Spells": "Auto-populated index of every spell described on the wiki. See [[NWN Reference]] for the curated portal page that groups spells by school and caster.",
    "NWN Feats": "Auto-populated index of every feat described on the wiki. See [[NWN Reference]] for the curated portal page.",
    "NWN Skills": "Auto-populated index of every skill described on the wiki. See [[NWN Reference]] for the curated portal page.",
    "NWN Races": "Auto-populated index of every race described on the wiki. See [[Races]] and [[NWN Reference]].",
    "NWN Classes": "Auto-populated index of every class described on the wiki. See [[Classes]] and [[NWN Reference]].",
    "NWN Master Feats": "Auto-populated index of master feats. A master feat is the parent of a family of weapon- or school-specific variants -- e.g. [[Weapon Focus]] groups [[Weapon Focus (longsword)]], [[Weapon Focus (rapier)]], etc.",
    "NWN Epic Feats": "Subset of [[:Category:NWN Feats]] flagged as epic (require character level 21+).",
    "NWN Playable Races": "Subset of [[:Category:NWN Races]] flagged playable in [[racialtypes.2da]].",
    "NWN Playable Classes": "Subset of [[:Category:NWN Classes]] flagged playable in [[classes.2da]] (i.e. selectable at character creation or level-up). Includes both base and prestige classes.",
    "NWN Spellcasting Classes": "Subset of [[:Category:NWN Classes]] flagged as spellcasters in [[classes.2da]].",
    "NWN Abjuration Spells": "Spells of the Abjuration school. See [[:Category:NWN Spells]] for the full alphabetical index.",
    "NWN Conjuration Spells": "Spells of the Conjuration school. See [[:Category:NWN Spells]] for the full alphabetical index.",
    "NWN Divination Spells": "Spells of the Divination school. See [[:Category:NWN Spells]] for the full alphabetical index.",
    "NWN Enchantment Spells": "Spells of the Enchantment school. See [[:Category:NWN Spells]] for the full alphabetical index.",
    "NWN Evocation Spells": "Spells of the Evocation school. See [[:Category:NWN Spells]] for the full alphabetical index.",
    "NWN Illusion Spells": "Spells of the Illusion school. See [[:Category:NWN Spells]] for the full alphabetical index.",
    "NWN Necromancy Spells": "Spells of the Necromancy school. See [[:Category:NWN Spells]] for the full alphabetical index.",
    "NWN Transmutation Spells": "Spells of the Transmutation school. See [[:Category:NWN Spells]] for the full alphabetical index.",
    "NWN General Spells": "Spells with no school (e.g. spell-like abilities exposed as castable spells). See [[:Category:NWN Spells]] for the full alphabetical index.",
    "NWN Bard Spells": "Spells castable by bards. See [[:Category:NWN Spells]] for the full alphabetical index.",
    "NWN Cleric Spells": "Spells castable by clerics. See [[:Category:NWN Spells]] for the full alphabetical index.",
    "NWN Druid Spells": "Spells castable by druids. See [[:Category:NWN Spells]] for the full alphabetical index.",
    "NWN Paladin Spells": "Spells castable by paladins. See [[:Category:NWN Spells]] for the full alphabetical index.",
    "NWN Ranger Spells": "Spells castable by rangers. See [[:Category:NWN Spells]] for the full alphabetical index.",
    "NWN Wizard and Sorceror Spells": "Spells castable by wizards or sorcerers. See [[:Category:NWN Spells]] for the full alphabetical index. (The historical 'Sorceror' misspelling is preserved to keep the existing wiki category intact.)",
}

# Footer added to every stub. Keeps the [[Category:NWN Reference]] umbrella
# tag consistent across all auto-bootstrapped category description pages,
# so [[:Category:NWN Reference]] becomes a "category of categories" hub.
FOOTER = "\n\n[[Category:NWN Reference]]"


def _collect_emitted_categories(tlk: TlkResolver) -> dict[str, str]:
    """Walk every record in every content type, union the categories each
    callable emits. Returns `{category_name: example_kind}` -- example_kind
    is just the first kind that produced this category, used for the
    fallback description."""
    out: dict[str, str] = {}
    for ct in CONTENT_TYPES:
        if ct.categories is None:
            continue
        records, _ = ct.loader(ct.layo_2da, tlk)
        for rec in records.values():
            for cat in ct.categories(rec):
                out.setdefault(cat, ct.kind)
    return out


def _missing_description_pages(client, names: list[str]) -> list[str]:
    """Return the subset of `names` whose Category:Name page has no wikitext
    yet. One API call per category -- small N, not worth batching."""
    missing: list[str] = []
    for name in names:
        wt = client.get_wikitext(f"Category:{name}")
        if wt is None or wt.strip() == "":
            missing.append(name)
    return missing


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="List what would be created; don't write to wiki")
    ap.add_argument("--filter", default=None,
                    help="Comma-separated category names to process (default: all)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-6s %(message)s")
    log = logging.getLogger("bootstrap_categories")

    tlk = TlkResolver(
        REPO_ROOT / "vendor/stock/dialog_subset.json",
        REPO_ROOT / "layonara.tlk.json",
    )

    log.info("walking registry to collect emitted categories...")
    emitted = _collect_emitted_categories(tlk)
    log.info("found %d distinct categories emitted by the sync", len(emitted))
    for name in sorted(emitted):
        log.info("  - %s", name)

    if args.filter:
        wanted = {s.strip() for s in args.filter.split(",")}
        emitted = {n: k for n, k in emitted.items() if n in wanted}
        log.info("filter narrowed to %d categories", len(emitted))

    backend = make_default_backend()
    if backend is None:
        log.error("no write backend configured. Set WIKI_CONTAINER (and "
                  "optionally WIKI_BOT_USER) for docker-exec mode, the "
                  "same env vars wiki_sync.py uses.")
        sys.exit(1)
    creds = WikiCreds(
        api_url=os.environ.get("WIKI_API_URL", "https://wiki.layonara.com/api.php"),
        username="", password="",
    )
    client = WikiClient(creds, write_backend=backend)
    log.info("write backend: %s (user=%s)",
             client.write_backend_name, backend.user)
    log.info("checking which categories need description pages...")
    missing = _missing_description_pages(client, sorted(emitted))
    log.info("%d of %d categories have no description page",
             len(missing), len(emitted))

    if not missing:
        log.info("nothing to do.")
        return

    for name in missing:
        desc = DESCRIPTIONS.get(name,
            f"Auto-populated index of NWN {emitted[name]}s. See "
            "[[NWN Reference]] for the curated portal page.")
        body = desc + FOOTER
        log.info("[%s] %s",
                 "DRY-RUN" if args.dry_run else "create",
                 f"Category:{name}")
        if args.dry_run:
            continue
        client.edit(
            title=f"Category:{name}",
            text=body,
            summary="bootstrap category description page",
        )

    log.info("done. %d categor%s %s.",
             len(missing),
             "y" if len(missing) == 1 else "ies",
             "would be created" if args.dry_run else "created")


if __name__ == "__main__":
    main()
