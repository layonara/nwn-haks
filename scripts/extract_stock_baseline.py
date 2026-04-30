"""Extract stock NWN:EE baseline data into vendor/stock/ for the wiki sync.

Reads from a local NWN:EE install (Steam by default) and produces, for every
ContentType registered in `scripts/lib/registry.py`:
    vendor/stock/<2da-name>            extracted via nwn_resman_extract
    vendor/stock/dialog_subset.json    only TLK rows referenced by any of them

Re-run this whenever Beamdog ships an NWN:EE patch that touches the data, or
whenever a new ContentType is added to the registry.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import rollnw

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR = REPO_ROOT / "vendor" / "stock"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from lib.registry import CONTENT_TYPES  # noqa: E402

DEFAULT_NWN_ROOT = Path.home() / ".local/share/Steam/steamapps/common/Neverwinter Nights"
DEFAULT_USER_DIR = Path.home() / "dev/nwn/local-server/home"


def run_resman(nwn_root: Path, user_dir: Path, pattern: str, dest: Path) -> None:
    cmd = [
        "nwn_resman_extract", "--quiet",
        "--root", str(nwn_root),
        "--userdirectory", str(user_dir),
        "--pattern", pattern,
        "-d", str(dest),
    ]
    subprocess.run(cmd, check=True)


def tlk_to_json(tlk_path: Path, dest: Path) -> None:
    cmd = ["nwn_tlk", "-l", "tlk", "-k", "json", "-i", str(tlk_path), "-o", str(dest)]
    subprocess.run(cmd, check=True)


def collect_referenced_strrefs(twoda_path: Path, cols: tuple[str, ...]) -> set[int]:
    with twoda_path.open() as f:
        tda = rollnw.TwoDA.from_string(f.read())
    refs: set[int] = set()
    col_idxs = []
    for c in cols:
        try:
            col_idxs.append(tda.column_index(c))
        except Exception:
            print(f"warn: {twoda_path.name} has no column {c}", file=sys.stderr)
    for r in range(tda.rows()):
        for ci in col_idxs:
            v = tda.get_raw(r, ci)
            if v and v != "****":
                try:
                    refs.add(int(v))
                except ValueError:
                    pass
    return refs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nwn-root", default=os.environ.get("NWN_ROOT", str(DEFAULT_NWN_ROOT)))
    ap.add_argument("--user-dir", default=os.environ.get("NWN_USERDIR", str(DEFAULT_USER_DIR)))
    args = ap.parse_args()

    nwn_root = Path(args.nwn_root)
    user_dir = Path(args.user_dir)
    if not nwn_root.exists():
        print(f"error: nwn root not found: {nwn_root}", file=sys.stderr)
        return 1

    VENDOR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        all_refs: set[int] = set()
        for ct in CONTENT_TYPES:
            if ct.stock_2da is None:
                continue
            twoda_name = ct.stock_2da.name
            print(f"  extracting {twoda_name} ({ct.kind}) ...")
            run_resman(nwn_root, user_dir, twoda_name, tdp)
            src = tdp / twoda_name
            if not src.exists():
                print(f"error: {twoda_name} did not extract", file=sys.stderr)
                return 1
            shutil.copy2(src, VENDOR / twoda_name)
            refs = collect_referenced_strrefs(VENDOR / twoda_name, ct.tlk_columns)
            all_refs |= refs
            print(f"    -> {len(refs)} TLK strrefs from columns {ct.tlk_columns}")
        all_refs = {r for r in all_refs if r < 16_777_216}
        print(f"  total stock strrefs to capture: {len(all_refs)}")

        tlk_src = nwn_root / "lang" / "en" / "data" / "dialog.tlk"
        tlk_full = tdp / "dialog.tlk.json"
        print(f"  converting {tlk_src.name} -> json ...")
        tlk_to_json(tlk_src, tlk_full)
        with tlk_full.open() as f:
            data = json.load(f)
        keep = [e for e in data["entries"] if e["id"] in all_refs]
        subset = {"language": data["language"], "entries": keep}
        with (VENDOR / "dialog_subset.json").open("w") as f:
            json.dump(subset, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  wrote dialog_subset.json with {len(keep)} entries")

    readme = VENDOR / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Stock NWN:EE baseline\n\n"
            "Vendored snapshot of the stock NWN:EE 2da/tlk used to diff Layonara overrides for the\n"
            "wiki sync (`scripts/wiki_sync.py`). Re-extract by running:\n\n"
            "    python3 scripts/extract_stock_baseline.py\n\n"
            "(Defaults to the Steam install at `~/.local/share/Steam/steamapps/common/Neverwinter Nights`.\n"
            "Override with `--nwn-root` or `$NWN_ROOT`.)\n"
        )
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
