"""Sync Layonara 2da/tlk-driven content to wiki.layonara.com.

The set of content types (spells, feats, classes, races, ...) lives in
`scripts/lib/registry.py`; this script walks that registry without any
per-type special-cases.

Usage:
    # Dry run (no writes; render targets to /tmp/wiki_sync_diffs/):
    python3 scripts/wiki_sync.py --dry-run --filter Acid_Fog,Bestow_Curse

    # Live, but only two specific entries:
    python3 scripts/wiki_sync.py --filter Acid_Fog,Bestow_Curse \\
        --commit "$GITHUB_SHA"

    # Restrict to one or more content types:
    python3 scripts/wiki_sync.py --kinds spell,feat

Write authentication, in priority order:
  1. WIKI_CONTAINER  -- shells into the wiki container's maintenance/edit.php
                        (no MediaWiki bot password needed; this is what the
                        aragen bot's changelog cog does and what we should
                        keep using until/unless somebody refreshes the bot
                        password at https://wiki.layonara.com/Special:BotPasswords).
                        Optional companion: WIKI_SSH_HOST to proxy via ssh.
  2. WIKI_BOT_USER + WIKI_BOT_PASSWORD -- classic MediaWiki BotPasswords API
                        login. Currently broken on production (wrongpassword
                        in Coolify); this branch exists for future use.

Reads (existing-page fetch + image enumeration) always go through the public
action=query API and need no auth.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lib.tlk import TlkResolver  # noqa: E402
from lib.registry import (  # noqa: E402
    CONTENT_TYPES, AUX_LOADERS, get_template_names,
)
from lib.render import (  # noqa: E402
    render_identical, render_modified, render_custom, render_clean_header,
    splice_into_page, diff_records,
)
from lib.spell_record import set_known_icon_files  # noqa: E402
from lib.wiki_client import WikiClient, WikiCreds, make_default_backend  # noqa: E402


LAYO_TLK_JSON = REPO_ROOT / "layonara.tlk.json"
STOCK_TLK_JSON = REPO_ROOT / "vendor/stock/dialog_subset.json"

DIFF_DUMP_DIR = Path("/tmp/wiki_sync_diffs")


def _page_title(record) -> str:
    """The wiki page title for a record is its resolved TLK name (the in-game
    name). The 2da LABEL column is just a human-readable mnemonic within the
    file and must not be used for player-facing routing."""
    return record.name


def _label_to_name_distance(label: str, name: str) -> int:
    """How "close" a 2da LABEL is to the resolved in-game NAME. Lower is better.

    Used to pick a canonical record when multiple rows resolve to the same wiki
    page title (e.g. several feat.2da rows whose Name strref points at the same
    TLK string). The label that most closely matches the name is the player-
    facing one; NPC/internal variants get suffixes or unrelated codenames.
    """
    norm_label = label.lower().replace("_", "").replace(" ", "").replace("-", "")
    norm_name = name.lower().replace("_", "").replace(" ", "").replace("-", "")
    if norm_label == norm_name:
        return 0
    if norm_label.startswith(norm_name) or norm_name.startswith(norm_label):
        return 1
    if norm_name in norm_label:
        return 2
    return 100  # totally unrelated (e.g. label="VEIL" name="Elf")


def _is_canonical(rec) -> int:
    """Bonus (0 better than 1) for records whose `PlayerRace=1` / `PlayerClass=1`
    flag explicitly marks them as the canonical player-facing entry. For record
    types without that flag, returns 0."""
    if getattr(rec, "player_race", None) is True:
        return 0
    if getattr(rec, "player_class", None) is True:
        return 0
    if getattr(rec, "player_race", None) is False:
        return 2
    if getattr(rec, "player_class", None) is False:
        return 2
    return 1


def _pick_canonical(label_records: list[tuple[str, object]]) -> tuple[str, object]:
    """Of all (label, record) entries that resolve to the same page title,
    pick the canonical one: prefer (a) PlayerRace/PlayerClass=1, (b) the
    label whose spelling most closely matches the name, (c) smallest label
    (deterministic fallback)."""
    return min(
        label_records,
        key=lambda lr: (_is_canonical(lr[1]),
                        _label_to_name_distance(lr[0], lr[1].name),
                        lr[0]),
    )


def _build_blocks_for(entries_layo: dict, entries_stock: dict, display_fields,
                      filter_terms: set[str] | None,
                      skipped_no_name: list[str],
                      collisions: list[tuple[str, str, list[str]]],
                      kind: str) -> dict[str, tuple[str, object]]:
    """Return {label: (managed_block_wikitext, layo_record)} for each requested entry.

    `filter_terms` may contain 2da LABELs and/or in-game names; both match.
    Records whose `.name` is empty (TLK ref missing or "Bad StrRef") are
    skipped and reported in `skipped_no_name`.

    When multiple records resolve to the same page title, the canonical row
    (see _pick_canonical) is kept and the rest are reported in `collisions`.
    """
    # First pass: filter + skip bad names + group by resolved page title.
    by_title: dict[str, list[tuple[str, object]]] = {}
    for label, layo_rec in entries_layo.items():
        if filter_terms is not None:
            if label not in filter_terms and layo_rec.name not in filter_terms:
                continue
        if not layo_rec.name or layo_rec.name.lower() == "bad strref":
            skipped_no_name.append(label)
            continue
        by_title.setdefault(_page_title(layo_rec), []).append((label, layo_rec))

    blocks: dict[str, tuple[str, object]] = {}
    for title, candidates in by_title.items():
        if len(candidates) > 1:
            chosen = _pick_canonical(candidates)
            losers = [lab for lab, _ in candidates if lab != chosen[0]]
            collisions.append((kind, title, [chosen[0], *losers]))
        else:
            chosen = candidates[0]
        label, layo_rec = chosen
        stock_rec = entries_stock.get(label)
        deltas = diff_records(layo_rec, stock_rec, display_fields)
        if stock_rec is None:
            block = render_custom(layo_rec, display_fields)
        elif not deltas:
            block = render_identical(layo_rec, display_fields)
        else:
            block = render_modified(layo_rec, stock_rec, display_fields, set(deltas))
        blocks[label] = (block, layo_rec)
    return blocks


def _load_all(tlk: TlkResolver, log: logging.Logger):
    """Load every ContentType (Layo + stock) and every aux loader.

    Returns three things:
      records[kind] = (layo_records, stock_records)        # only ContentTypes
      layo_id_maps[kind] = {row: name}                     # CT + aux
      stock_id_maps[kind] = {row: name}                    # CT only (aux side
                                                              tables don't need
                                                              a stock copy)
    """
    records: dict[str, tuple[dict, dict]] = {}
    layo_id_maps: dict[str, dict[int, str]] = {}
    stock_id_maps: dict[str, dict[int, str]] = {}

    for ct in CONTENT_TYPES:
        log.info("loading %s (Layonara + stock) ...", ct.kind)
        layo, layo_ids = ct.loader(ct.layo_2da, tlk)
        if ct.stock_2da and ct.stock_2da.exists():
            stock, stock_ids = ct.loader(ct.stock_2da, tlk)
        else:
            stock, stock_ids = {}, {}
        records[ct.kind] = (layo, stock)
        layo_id_maps[ct.kind] = layo_ids
        stock_id_maps[ct.kind] = stock_ids

    for kind, path, loader in AUX_LOADERS:
        log.info("loading aux table %s ...", kind)
        layo_id_maps[kind] = loader(path, tlk)
        # Aux tables (e.g. masterfeats) are rarely customised; reuse the same
        # name map for stock-side xref resolution unless a stock copy exists.
        stock_id_maps[kind] = layo_id_maps[kind]

    return records, layo_id_maps, stock_id_maps


def _link_xrefs(records, layo_id_maps, stock_id_maps, log):
    """Run each ContentType's xref linker on both Layo and stock records."""
    for ct in CONTENT_TYPES:
        if ct.xref_link is None:
            continue
        layo, stock = records[ct.kind]
        log.debug("linking xrefs for %s ...", ct.kind)
        ct.xref_link(layo, layo_id_maps)
        ct.xref_link(stock, stock_id_maps)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="don't touch the wiki; render blocks to %s and print summary"
                         % DIFF_DUMP_DIR)
    ap.add_argument("--filter", default="",
                    help="comma-separated entries to sync. Each item may be either a "
                         "2da LABEL (e.g. Acid_Fog) or the in-game name (e.g. 'Weapon "
                         "Finesse'). If unset, syncs everything.")
    ap.add_argument("--kinds", default="",
                    help="comma-separated content kinds to include "
                         "(e.g. 'spell,feat,class'). Default: all registered kinds.")
    ap.add_argument("--limit", type=int, default=0,
                    help="if non-zero, sync at most N entries per kind (after filtering)")
    ap.add_argument("--commit", default=os.environ.get("GITHUB_SHA", "local"),
                    help="commit sha cited in the edit summary")
    ap.add_argument("--clear-existing-desc", action="store_true",
                    help="rewrite the existing template `desc=...` parameter "
                         "(or freeform prose) on existing pages to a pointer "
                         "stub, so the autosync block is the sole source of "
                         "truth. Use with care -- destroys human prose. "
                         "Default: leave existing prose intact above the block.")
    ap.add_argument("--no-create", action="store_true",
                    help="only edit pages that already exist on the wiki; "
                         "skip records whose target page would be created. "
                         "Useful for staged rollouts where you want to update "
                         "existing community pages first and decide later "
                         "which subset of new pages to create.")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    log = logging.getLogger("wiki_sync")

    requested_kinds = {k.strip() for k in args.kinds.split(",") if k.strip()}
    active_types = [ct for ct in CONTENT_TYPES
                    if not requested_kinds or ct.kind in requested_kinds]
    if requested_kinds:
        unknown = requested_kinds - {ct.kind for ct in CONTENT_TYPES}
        if unknown:
            log.error("unknown --kinds: %s. registered: %s",
                      sorted(unknown), [ct.kind for ct in CONTENT_TYPES])
            return 2
    log.info("active content types: %s", [ct.kind for ct in active_types])

    filter_terms = set(s.strip() for s in args.filter.split(",") if s.strip()) or None

    log.info("loading TLK ...")
    tlk = TlkResolver(stock_path=STOCK_TLK_JSON, custom_path=LAYO_TLK_JSON)

    records, layo_id_maps, stock_id_maps = _load_all(tlk, log)
    _link_xrefs(records, layo_id_maps, stock_id_maps, log)

    # Build the icon-existence whitelist by scanning the wiki's File: namespace
    # for the icon prefixes we use. Records whose icon isn't on the wiki yet
    # render as `<code>resref</code>` only (no broken-image link).
    icon_prefixes = sorted({
        ct.get_icon(rec).split("_", 1)[0] + "_"
        for ct in active_types
        for rec in records[ct.kind][0].values()
        if ct.icon_attr and ct.get_icon(rec) and "_" in ct.get_icon(rec)
    })
    if icon_prefixes:
        log.info("scanning wiki for icon files (prefixes=%s) ...", icon_prefixes)
        ro_creds = WikiCreds(
            api_url=os.environ.get("WIKI_API_URL", "https://wiki.layonara.com/api.php"),
            username="", password="",
        )
        try:
            known = WikiClient(ro_creds).list_image_files(icon_prefixes)
            log.info("  %d icon files known to the wiki", len(known))
            set_known_icon_files(known)
        except Exception as e:
            log.warning("could not enumerate wiki icon files (%s); rendering all "
                        "[[File:...]] links unconditionally", e)

    # blocks_per_kind[kind] = {label: (block_text, layo_record)}
    blocks_per_kind: dict[str, dict[str, tuple[str, object]]] = {}
    skipped_no_name: list[str] = []
    collisions: list[tuple[str, str, list[str]]] = []
    for ct in active_types:
        layo, stock = records[ct.kind]
        blocks = _build_blocks_for(layo, stock, ct.display_fields,
                                   filter_terms, skipped_no_name,
                                   collisions, ct.kind)
        if args.limit:
            blocks = dict(list(blocks.items())[:args.limit])
        blocks_per_kind[ct.kind] = blocks
        log.info("  prepared %d %s blocks", len(blocks), ct.kind)

    if skipped_no_name:
        log.warning("skipped %d records with empty/Bad StrRef names: %s%s",
                    len(skipped_no_name),
                    ", ".join(skipped_no_name[:10]),
                    " ..." if len(skipped_no_name) > 10 else "")

    if collisions:
        log.warning("page-title collisions resolved by canonical-row picking: %d",
                    len(collisions))
        for kind, title, labels in collisions[:15]:
            log.warning("  [%s] %r: kept %r, skipped %s",
                        kind, title, labels[0], labels[1:])
        if len(collisions) > 15:
            log.warning("  ... and %d more", len(collisions) - 15)

    template_names = get_template_names()

    if args.dry_run:
        DIFF_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        creds = WikiCreds(
            api_url=os.environ.get("WIKI_API_URL", "https://wiki.layonara.com/api.php"),
            username="", password="",
        )
        ro = WikiClient(creds)
        for ct in active_types:
            for label, (block, record) in blocks_per_kind[ct.kind].items():
                title = _page_title(record)
                try:
                    existing = ro.get_wikitext(title)
                except Exception as e:
                    log.warning("[%s] %s: could not fetch existing (%s); showing block only",
                                ct.kind, title, e)
                    existing = None
                clean_header = render_clean_header(
                    ct.template_name, record.name, ct.get_icon(record))
                spliced = splice_into_page(existing, block,
                                           clear_existing_desc=args.clear_existing_desc,
                                           clean_header=clean_header,
                                           template_names=template_names)
                safe = "".join(c if c.isalnum() else "_" for c in title)[:60]
                out = DIFF_DUMP_DIR / f"{ct.kind}_{safe}.wiki"
                marker = "EXISTING PAGE FOUND" if existing else "NEW PAGE WOULD BE CREATED"
                header = (
                    f"# target page: {title}\n"
                    f"# (kind: {ct.kind}; 2da label: {label})\n"
                    f"# {marker}\n"
                    f"# block size: {len(block)} chars; spliced page size: {len(spliced)} chars\n\n"
                )
                out.write_text(header + spliced + "\n")
                log.info("  wrote %s  (%s)", out, marker.lower())
        log.info("dry-run complete; %s rendered to %s",
                 ", ".join(f"{len(blocks_per_kind[ct.kind])} {ct.kind}" for ct in active_types),
                 DIFF_DUMP_DIR)
        return 0

    backend = make_default_backend()
    if backend is not None:
        creds = WikiCreds(
            api_url=os.environ.get("WIKI_API_URL", "https://wiki.layonara.com/api.php"),
            username="", password="",
        )
        client = WikiClient(creds, write_backend=backend)
        log.info("write backend: %s (user=%s%s)",
                 client.write_backend_name, backend.user,
                 f", via ssh {backend.ssh_host}" if backend.ssh_host else "")
    else:
        if not (os.environ.get("WIKI_BOT_USER") and os.environ.get("WIKI_BOT_PASSWORD")):
            raise SystemExit(
                "no write path configured. Set either:\n"
                "  WIKI_CONTAINER (preferred; uses docker exec edit.php like the bot does)\n"
                "  -- or --\n"
                "  WIKI_BOT_USER + WIKI_BOT_PASSWORD (MediaWiki BotPasswords API; "
                "currently broken on production -- password in Coolify is stale)")
        creds = WikiCreds(
            api_url=os.environ.get("WIKI_API_URL", "https://wiki.layonara.com/api.php"),
            username=os.environ["WIKI_BOT_USER"],
            password=os.environ["WIKI_BOT_PASSWORD"],
        )
        client = WikiClient(creds)
        log.info("write backend: api (logging in as %s)", creds.username)
        client.login()

    n_changed = n_unchanged = n_created = n_skipped_no_create = n_errors = 0

    for ct in active_types:
        for label, (block, record) in blocks_per_kind[ct.kind].items():
            title = _page_title(record)
            try:
                existing = client.get_wikitext(title)
                if existing is None and args.no_create:
                    log.info("[%s] %s: SKIPPED (--no-create; page does not exist)",
                             ct.kind, title)
                    n_skipped_no_create += 1
                    continue
                clean_header = render_clean_header(
                    ct.template_name, record.name, ct.get_icon(record))
                new_text = splice_into_page(existing, block,
                                            clear_existing_desc=args.clear_existing_desc,
                                            clean_header=clean_header,
                                            template_names=template_names)
                if existing is not None and new_text == existing:
                    log.info("[%s] %s: unchanged", ct.kind, title)
                    n_unchanged += 1
                    continue
                summary = (f"layonara wiki-sync: {ct.kind} {label} "
                           f"@ nwn-haks {args.commit[:8]}")
                result = client.edit(title, new_text, summary,
                                     bot=True, create_only=False, no_create=False)
                if existing is None:
                    log.info("[%s] %s: CREATED (revid=%s)", ct.kind, title,
                             result.get("newrevid"))
                    n_created += 1
                else:
                    log.info("[%s] %s: edited (revid=%s)", ct.kind, title,
                             result.get("newrevid"))
                    n_changed += 1
            except Exception as e:
                log.error("[%s] %s: ERROR %s", ct.kind, title, e)
                n_errors += 1

    log.info("done. %d edited, %d created, %d unchanged, %d skipped (no-create), "
             "%d errors", n_changed, n_created, n_unchanged, n_skipped_no_create,
             n_errors)
    return 1 if n_errors else 0


if __name__ == "__main__":
    sys.exit(main())
