"""Word-level diff renderer for the two-column comparison table.

Wraps tokens that exist on one side but not the other in <ins>/<del> tags so
MediaWiki renders them with underline / strikethrough plus a visible color.

Tokenization keeps whitespace runs and explicit line breaks as separate tokens
so the diff stays stable across reflow.
"""
from __future__ import annotations

import difflib
import re

# Light-yellow row already covers the cell; make the inline marks pop further.
INS_OPEN = '<ins style="background:#c6efce; text-decoration:none; padding:0 2px;">'
INS_CLOSE = "</ins>"
DEL_OPEN = '<del style="background:#ffc7ce; text-decoration:line-through; padding:0 2px;">'
DEL_CLOSE = "</del>"

_TOKEN_RE = re.compile(r"\s+|[^\s]+")


def _tokenize(s: str) -> list[str]:
    """Split into a list of (whitespace | non-whitespace) tokens preserving order."""
    if not s:
        return []
    return _TOKEN_RE.findall(s)


def _wrap_run(tokens: list[str], open_tag: str, close_tag: str) -> str:
    """Wrap a run of tokens in a single open/close pair (avoids one wrapper per
    token, which would render hideously). Whitespace at run boundaries is kept
    OUTSIDE the wrapper so the markers don't engulf surrounding spaces."""
    if not tokens:
        return ""
    # Trim leading/trailing whitespace tokens out of the wrapper.
    lead, trail = "", ""
    while tokens and tokens[0].isspace():
        lead += tokens.pop(0)
    while tokens and tokens[-1].isspace():
        trail = tokens.pop() + trail
    if not tokens:
        return lead + trail
    return lead + open_tag + "".join(tokens) + close_tag + trail


def word_diff(layo_text: str, stock_text: str) -> tuple[str, str]:
    """Return (layo_marked, stock_marked) where text differences are inline-tagged.

    layo_marked   :  <ins>...</ins> wraps words present in Layonara but not stock.
    stock_marked  :  <del>...</del> wraps words present in stock but not Layonara.
    """
    a = _tokenize(layo_text)
    b = _tokenize(stock_text)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    layo_out: list[str] = []
    stock_out: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            chunk = "".join(a[i1:i2])
            layo_out.append(chunk)
            stock_out.append(chunk)
        elif tag == "replace":
            layo_out.append(_wrap_run(list(a[i1:i2]), INS_OPEN, INS_CLOSE))
            stock_out.append(_wrap_run(list(b[j1:j2]), DEL_OPEN, DEL_CLOSE))
        elif tag == "delete":
            # in Layonara but not stock -> Layonara added it.
            layo_out.append(_wrap_run(list(a[i1:i2]), INS_OPEN, INS_CLOSE))
        elif tag == "insert":
            # in stock but not Layonara -> Layonara removed it.
            stock_out.append(_wrap_run(list(b[j1:j2]), DEL_OPEN, DEL_CLOSE))
    return "".join(layo_out), "".join(stock_out)
