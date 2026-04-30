"""Bulk-upload icons referenced by the wiki-synced 2da content to wiki.layonara.com.

Why: `wiki_sync.py` emits `[[File:<resref>.png]]` tags in the autosync block.
If the file isn't on the wiki, the page shows a broken-image link. This
script makes sure every icon resref referenced by any registered ContentType
has a matching PNG uploaded to the wiki.

Source resolution per icon resref:
  1. `nwn-haks/icons/<resref>.{tga,dds,plt}` (Layonara override, in-hak)
  2. `nwn-haks/unsorted/<resref>.{tga,dds,plt}` (Layonara override, not-yet-haked)
  3. `nwn_resman_extract --pattern <resref>` against the stock NWN install

Conversion: NWN icon TGAs are 64x128 RGBA (the visible 64x64 sits on top, the
bottom 64x64 is the alternate/disabled state). We crop to the top 64x64 and
emit a PNG.

Upload: PNGs are imported via the wiki container's `maintenance/importImages.php
--skip-dupes` (idempotent re-runs are safe). The wiki container is reached
either directly (when running on the leanthar host itself, e.g. from CI) or via
SSH+rsync (when running from a developer workstation).

Usage:
    # Dry run: collect resrefs, resolve sources, convert -- but don't upload.
    python3 scripts/upload_icons.py --dry-run

    # Restrict to one or more content types:
    python3 scripts/upload_icons.py --kinds class,skill

    # Full upload (auto-detects local docker if you're on leanthar):
    python3 scripts/upload_icons.py

    # Force the SSH path even on leanthar:
    python3 scripts/upload_icons.py --ssh-host orth@5.161.122.37

Requires: nwn_resman_extract + ImageMagick (`convert`) on whichever host runs
this script. When using SSH mode you also need rsync on both ends.
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lib.tlk import TlkResolver  # noqa: E402
from lib.registry import CONTENT_TYPES  # noqa: E402

ICON_OVERRIDE_DIRS = [REPO_ROOT / "icons", REPO_ROOT / "unsorted"]


def _first_existing(*candidates: Path) -> Path:
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


# NWN install + user-dir auto-detection. Override with NWN_ROOT / NWN_USER env
# vars when running outside one of these well-known layouts. The leanthar
# layo-haks setup keeps NWN data under /opt/layonara/nwn-data/; rofirein and
# laptops use the Steam install under ~/.local/share.
NWN_ROOT = Path(os.environ.get("NWN_ROOT")) if os.environ.get("NWN_ROOT") else _first_existing(
    Path("/opt/layonara/nwn-data/nwn"),
    Path.home() / ".local/share/Steam/steamapps/common/Neverwinter Nights",
)
NWN_USER = Path(os.environ.get("NWN_USER")) if os.environ.get("NWN_USER") else _first_existing(
    Path("/opt/layonara/nwn-data"),
    Path.home() / "dev/nwn/local-server/home",
)

WIKI_CONTAINER = "y82pthxjr38wth284d78m4cj-033153645823"
LOCAL_STAGING = "/tmp/wiki_icon_upload"


def collect_needed_resrefs(active_kinds: set[str]) -> dict[str, list[str]]:
    """Return {resref_lower: [kinds_that_use_it]}."""
    log = logging.getLogger("upload_icons")
    tlk = TlkResolver(stock_path=REPO_ROOT / "vendor/stock/dialog_subset.json",
                      custom_path=REPO_ROOT / "layonara.tlk.json")
    needed: dict[str, list[str]] = {}
    for ct in CONTENT_TYPES:
        if active_kinds and ct.kind not in active_kinds:
            continue
        if not ct.icon_attr:
            continue
        log.info("scanning %s ...", ct.kind)
        recs, _ = ct.loader(ct.layo_2da, tlk)
        for r in recs.values():
            icon = (getattr(r, ct.icon_attr, "") or "").lower()
            if icon:
                needed.setdefault(icon, []).append(ct.kind)
    return needed


def resolve_source(resref: str, extract_cache: dict[str, Path]) -> Path | None:
    """Find a TGA/DDS/PLT for `resref`. Cached extract dir holds bulk results
    from a single `nwn_resman_extract --pattern <resref>` invocation."""
    log = logging.getLogger("upload_icons")
    for d in ICON_OVERRIDE_DIRS:
        for ext in ("tga", "dds", "plt"):
            p = d / f"{resref}.{ext}"
            if p.exists():
                return p

    cached = extract_cache.get(resref)
    if cached is not None:
        return cached if cached.exists() else None

    with tempfile.TemporaryDirectory(prefix="nwn_icon_") as td:
        td_path = Path(td)
        cmd = ["nwn_resman_extract",
               "--root", str(NWN_ROOT),
               "--userdirectory", str(NWN_USER),
               "--pattern", resref,
               "-d", str(td_path), "--quiet"]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            log.warning("  extract failed for %s: %s", resref, e)
            extract_cache[resref] = Path("/dev/null/missing")
            return None
        candidates = sorted(p for p in td_path.iterdir()
                            if p.stem.lower() == resref
                            and p.suffix.lower() in (".tga", ".dds", ".plt"))
        if not candidates:
            extract_cache[resref] = Path("/dev/null/missing")
            return None
        # Stash the source in our long-lived cache dir (the temp dir dies on exit).
        cache_dir = Path(tempfile.gettempdir()) / "nwn_icon_cache"
        cache_dir.mkdir(exist_ok=True)
        keep = candidates[0]
        dst = cache_dir / keep.name
        shutil.copy2(keep, dst)
        extract_cache[resref] = dst
        return dst


def convert_to_png(src: Path, dst: Path) -> bool:
    """TGA/DDS/PLT -> PNG, cropped to top 64x64 (NWN icon visible region)."""
    log = logging.getLogger("upload_icons")
    cmd = ["convert", str(src),
           "-crop", "64x64+0+0", "+repage", str(dst)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=10)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.warning("  convert failed for %s: %s", src.name, e.stderr.decode()[:200] if hasattr(e, "stderr") else e)
        return False


def upload_directory(local_dir: Path, summary: str, dry_run: bool,
                     ssh_host: str | None) -> int:
    """Stage PNGs into the wiki container and run importImages.php --skip-dupes.

    If `ssh_host` is set, rsync to that host first then docker exec via SSH.
    Otherwise assume we're already on the same host as the wiki container and
    just docker cp + docker exec directly. Either way the import is idempotent.
    """
    log = logging.getLogger("upload_icons")
    n_files = sum(1 for _ in local_dir.glob("*.png"))
    log.info("uploading %d PNG file(s) to wiki (%s) ...", n_files,
             f"via ssh {ssh_host}" if ssh_host else "local docker")
    if dry_run:
        log.info("  [dry-run] skipping upload")
        return n_files

    if ssh_host:
        subprocess.run(["ssh", ssh_host,
                        f"rm -rf {LOCAL_STAGING} && mkdir -p {LOCAL_STAGING}"],
                       check=True)
        subprocess.run(["rsync", "-az", f"{local_dir}/",
                        f"{ssh_host}:{LOCAL_STAGING}/"],
                       check=True)
        staging = LOCAL_STAGING
    else:
        subprocess.run(["rm", "-rf", LOCAL_STAGING], check=True)
        subprocess.run(["cp", "-r", str(local_dir), LOCAL_STAGING], check=True)
        staging = LOCAL_STAGING

    docker_cmd = (
        f"docker cp {staging} {WIKI_CONTAINER}:/tmp/icon_upload "
        f"&& docker exec {WIKI_CONTAINER} php maintenance/importImages.php "
        f"--skip-dupes --user=Orth "
        f"--comment={subprocess.list2cmdline([summary])} "
        f"/tmp/icon_upload "
        f"&& docker exec {WIKI_CONTAINER} rm -rf /tmp/icon_upload"
    )
    if ssh_host:
        cmd = ["ssh", ssh_host, docker_cmd]
    else:
        cmd = ["sh", "-c", docker_cmd]
    log.info("running: %s", " ".join(cmd[:-1]) + " ...")
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("import failed: stdout=%s stderr=%s",
                  result.stdout[-500:], result.stderr[-500:])
        return 0
    log.info("import output (tail): %s", result.stdout[-1000:])
    return n_files


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="convert PNGs to a temp dir but skip the actual upload step")
    ap.add_argument("--kinds", default="",
                    help="comma-separated kinds to upload (default: all registered with icons)")
    ap.add_argument("--keep-temp", action="store_true",
                    help="don't delete the temp PNG output dir on exit "
                         "(useful for inspecting before upload)")
    ap.add_argument("--ssh-host", default=os.environ.get("WIKI_SSH_HOST", ""),
                    help="SSH user@host to proxy the docker exec through "
                         "(default: $WIKI_SSH_HOST or empty = run docker locally; "
                         "set this when running from a workstation that isn't the wiki host)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    log = logging.getLogger("upload_icons")

    active_kinds = {k.strip() for k in args.kinds.split(",") if k.strip()}

    if not NWN_ROOT.exists():
        log.error("NWN_ROOT does not exist: %s", NWN_ROOT)
        log.error("set NWN_ROOT env var to the Neverwinter Nights install dir")
        return 2

    needed = collect_needed_resrefs(active_kinds)
    log.info("total unique icon resrefs needed: %d", len(needed))
    if not needed:
        log.info("nothing to do")
        return 0

    out_dir = Path(tempfile.mkdtemp(prefix="nwn_icons_png_"))
    log.info("staging PNGs in %s", out_dir)

    extract_cache: dict[str, Path] = {}
    n_resolved = n_converted = n_missing = 0
    missing: list[str] = []

    for i, (resref, kinds) in enumerate(sorted(needed.items()), 1):
        if i % 50 == 0:
            log.info("  ... %d / %d processed", i, len(needed))
        src = resolve_source(resref, extract_cache)
        if src is None:
            n_missing += 1
            missing.append(resref)
            continue
        n_resolved += 1
        dst = out_dir / f"{resref}.png"
        if convert_to_png(src, dst):
            n_converted += 1

    log.info("resolved sources for %d / %d resrefs (%d missing)",
             n_resolved, len(needed), n_missing)
    log.info("converted %d sources to PNG", n_converted)

    if missing:
        log.warning("missing icon sources (first 30): %s",
                    missing[:30])
        if len(missing) > 30:
            log.warning("  ... and %d more", len(missing) - 30)

    if n_converted == 0:
        log.error("no PNGs produced; aborting upload")
        return 1

    summary = f"layonara wiki-sync: bulk icon upload ({n_converted} files)"
    n_uploaded = upload_directory(out_dir, summary, dry_run=args.dry_run,
                                  ssh_host=args.ssh_host or None)
    log.info("done (%d uploaded%s)", n_uploaded,
             " [dry-run]" if args.dry_run else "")

    if not args.keep_temp:
        shutil.rmtree(out_dir, ignore_errors=True)
    else:
        log.info("kept temp dir: %s", out_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
