# Stock NWN:EE baseline

Vendored snapshot of the stock NWN:EE 2da/tlk used to diff Layonara overrides for the
wiki sync (`scripts/wiki_sync.py`). Re-extract by running:

    python3 scripts/extract_stock_baseline.py

(Defaults to the Steam install at `~/.local/share/Steam/steamapps/common/Neverwinter Nights`.
Override with `--nwn-root` or `$NWN_ROOT`.)
