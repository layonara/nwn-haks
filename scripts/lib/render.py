"""Wikitext rendering for the AUTOSYNC managed block.

Three outcomes per row:
  * identical to stock          -> single-column stat block + 'Identical to stock' badge
  * differs from stock          -> two-column comparison table, differing rows highlighted
  * custom Layonara content     -> single-column stat block + 'Custom Layonara' badge
  * removed in Layonara         -> just a 'Removed in Layonara' notice

The block is wrapped in HTML comments so we can splice it in/out of pages whose
surrounding human prose we don't want to clobber.
"""
from __future__ import annotations

from typing import Callable, Optional

from .word_diff import word_diff

BEGIN_MARKER = "<!-- BEGIN-AUTOSYNC v1 -->"
END_MARKER = "<!-- END-AUTOSYNC -->"

HIGHLIGHT_STYLE = 'style="background:#fffacd;"'  # light goldenrod yellow
SOURCE_NOTE = (
    "<small>''Auto-generated from [https://github.com/Layonara/nwn-haks nwn-haks] "
    "(`config/2da/spells.2da`, `feat.2da`, `layonara.tlk`). Do not edit between the "
    "AUTOSYNC markers; edits will be overwritten on the next sync.''</small>"
)


def _esc(value: str) -> str:
    """Escape wikitext-significant characters in stat-block cells.

    We deliberately do not escape the description column since we want pre-existing
    markup (links, italics) from TLK descriptions to flow through.
    """
    if value is None:
        return ""
    s = str(value)
    if "\n" in s:
        # Convert hard line breaks so the table cell renders sanely
        s = s.replace("\n", "<br>")
    return s


def _row(label: str, value: str, highlight: bool = False) -> str:
    style = HIGHLIGHT_STYLE if highlight else ""
    return (
        f"|-{(' ' + style) if style else ''}\n"
        f"! style=\"text-align:left; width:18em;\" | {_esc(label)}\n"
        f"| {_esc(value)}\n"
    )


def _row_compare(label: str, layo: str, stock: str, highlight: bool) -> str:
    style = HIGHLIGHT_STYLE if highlight else ""
    # Inline word-diff when both sides have content AND they differ. For
    # truly-empty sides we use the (none) placeholder rather than diffing
    # an entire blob into <ins>/<del>.
    layo_disp = layo or "''(none)''"
    stock_disp = stock or "''(none)''"
    if highlight and layo and stock:
        layo_marked, stock_marked = word_diff(layo, stock)
        layo_disp, stock_disp = layo_marked, stock_marked
    return (
        f"|-{(' ' + style) if style else ''}\n"
        f"! style=\"text-align:left; width:14em;\" | {_esc(label)}\n"
        f"| style=\"width:42%;\" | {_esc(layo_disp)}\n"
        f"| style=\"width:42%;\" | {_esc(stock_disp)}\n"
    )


def render_identical(record_obj, display_fields: list[tuple[str, Callable]],
                     extra: str = "") -> str:
    """Single-column stat block.

    `extra` is wikitext appended after the table (and badge) but before the
    source-attribution note. Use it for sections that don't fit the per-field
    row layout, e.g. a master feat's `== Variants ==` bullet list.
    """
    rows = []
    for label, getter in display_fields:
        v = getter(record_obj)
        if v == "" or v is None:
            continue
        rows.append(_row(label, v))
    body = "{| class=\"wikitable\" style=\"width:100%; max-width:48em;\"\n" + "".join(rows) + "|}\n"
    badge = "<small>''Identical to stock NWN:EE.''</small>"
    return _wrap(body + "\n" + badge + _join_extra(extra) + "\n\n" + SOURCE_NOTE)


def render_custom(record_obj, display_fields: list[tuple[str, Callable]],
                  extra: str = "") -> str:
    """Single-column stat block with a custom-content badge."""
    rows = []
    for label, getter in display_fields:
        v = getter(record_obj)
        if v == "" or v is None:
            continue
        rows.append(_row(label, v))
    body = "{| class=\"wikitable\" style=\"width:100%; max-width:48em;\"\n" + "".join(rows) + "|}\n"
    badge = "<small>''Custom Layonara content (no stock NWN:EE equivalent).''</small>"
    return _wrap(body + "\n" + badge + _join_extra(extra) + "\n\n" + SOURCE_NOTE)


def render_modified(layo, stock, display_fields: list[tuple[str, Callable]],
                    deltas: set[str], extra: str = "") -> str:
    """Two-column comparison table; differing rows highlighted, with inline
    word-level diff annotations on the differing cells."""
    rows = []
    for label, getter in display_fields:
        a = getter(layo)
        b = getter(stock)
        if a == "" and b == "":
            continue
        rows.append(_row_compare(label, a, b, highlight=label in deltas))
    body = (
        "{| class=\"wikitable\" style=\"width:100%;\"\n"
        "|-\n! style=\"width:14em;\" | Field !! Layonara !! Stock NWN:EE\n"
        + "".join(rows)
        + "|}\n"
    )
    n = len(deltas)
    legend = (
        "<small>''Differs from stock NWN:EE in "
        f"{n} field{'s' if n != 1 else ''}. "
        "Highlighted rows show changes; "
        '<ins style="background:#c6efce;">added</ins> and '
        '<del style="background:#ffc7ce;">removed</del> '
        "words are marked inline within differing cells.''</small>"
    )
    return _wrap(body + "\n" + legend + _join_extra(extra) + "\n\n" + SOURCE_NOTE)


def render_removed(label: str) -> str:
    body = (
        f"<div class=\"hatnote\">''This entry (`{_esc(label)}`) was removed in Layonara "
        "and is no longer available in-game. Page kept for reference.''</div>"
    )
    return _wrap(body + "\n\n" + SOURCE_NOTE)


def _join_extra(extra: str) -> str:
    """Pad an extra-content block with surrounding whitespace, or yield ''."""
    if not extra:
        return ""
    return "\n\n" + extra.strip()


def _wrap(body: str) -> str:
    return f"{BEGIN_MARKER}\n{body.strip()}\n{END_MARKER}"


DESC_STUB = "''(See auto-generated stat block below.)''"


def diff_records(layo, stock, display_fields: list[tuple[str, Callable]]) -> list[str]:
    """Return the list of display-field labels that differ between Layonara
    and stock. A None stock means the record is custom-added by Layonara
    (no equivalent in the vanilla game) -- every label counts as a "delta"
    in that case so render_custom can flag the whole row.
    """
    if stock is None:
        return [name for name, _ in display_fields]
    deltas: list[str] = []
    for name, getter in display_fields:
        if getter(layo) != getter(stock):
            deltas.append(name)
    return deltas


def render_clean_header(template_name: str, record_name: str, icon_resref: str) -> str:
    """Build a fresh `{{NWN:Spell|name=...|desc=STUB}}` invocation.

    The icon is rendered inside the autosync table now, not by the template, so
    we no longer pass `|icon=` here. (The argument is still accepted for
    backwards compatibility with callers that haven't been updated.)

    Used both as the seed for brand-new pages and as the prose replacement when
    `--clear-existing-desc` is set on a page that previously had no template
    (e.g. the freeform-prose-style feat pages). Trailing newlines included so
    the autosync block can splice immediately after.
    """
    del icon_resref  # intentionally unused -- table renders the icon row now
    parts = ["{{" + template_name, f"|name={record_name}",
             f"|desc=\n{DESC_STUB}\n}}}}"]
    return "\n".join(parts) + "\n\n"


def splice_into_page(existing_wikitext: Optional[str], new_block: str,
                     fallback_template: str | None = None,
                     clear_existing_desc: bool = False,
                     clean_header: str | None = None,
                     template_names: tuple[str, ...] = ()) -> str:
    """Replace an existing AUTOSYNC block in `existing_wikitext` with `new_block`.

    The block must NOT live inside any `{{<template>|desc=...}}` parameter:
    our wikitable markup is full of `|` characters, which would prematurely
    terminate the parameter and corrupt the page. Instead we inject immediately
    after the closing `}}` of any of the `template_names` invocations on the
    page, before the [[Category:...]] tail. Hand-curated `desc=` content stays
    intact and renders normally above our autosync block.

    `template_names` -- e.g. `("NWN:Spell", "NWN:Feat", "NWN:Class")`. When the
    caller doesn't pass any, no `{{...}}` parameter rewriting is performed and
    the block is simply appended after categories.

    If `clear_existing_desc` is True we additionally rewrite the template's
    `desc=...` parameter (between `desc=` and the next `|` at the same brace
    depth, OR `}}`) to a short pointer stub. Non-template freeform pages get
    the same treatment by replacing everything between the template-or-page
    start and the autosync block with the stub.

    If no markers and no template are present, fall back to:
      * existing_wikitext is None + fallback_template set: render the fallback.
      * otherwise: append the block at the end of the page.
    """
    if existing_wikitext is None:
        # Brand-new page: prefer the per-record clean_header (real name + icon)
        # over the static fallback_template that has empty `name=|icon=` values.
        if clean_header is not None:
            return clean_header + new_block + "\n"
        if fallback_template is None:
            return new_block
        return fallback_template.replace("__AUTOSYNC__", new_block)

    text = existing_wikitext
    template_was_cleared = False
    if clear_existing_desc and template_names:
        text, template_was_cleared = _clear_template_desc(text, template_names)

    if BEGIN_MARKER in text and END_MARKER in text:
        before, _, rest = text.partition(BEGIN_MARKER)
        _, _, after = rest.partition(END_MARKER)
        # Freeform prose pages (no template) keep their prose in `before`;
        # when clearing, swap it for either a fresh template invocation
        # (so the wiki template can do its own rendering) or the bare stub.
        if clear_existing_desc and not template_was_cleared:
            before = clean_header if clean_header is not None else DESC_STUB + "\n\n"
        return before + new_block + after

    # No marker yet -- inject after the closing `}}` of any known template
    # invocation, if one exists.
    insert_at = _find_template_close(text, template_names) if template_names else None
    if insert_at is not None:
        return (text[:insert_at]
                + "\n\n" + new_block + "\n\n"
                + text[insert_at:])

    # No template either -- append at the end (before any trailing categories).
    # When clearing, drop everything before the categories too AND prepend the
    # clean_header so freeform-prose pages still get a proper template wrapper
    # on first sync.
    header = clean_header if (clear_existing_desc and clean_header) else ""
    cat_idx = text.find("[[Category:")
    if cat_idx == -1:
        cat_idx = text.find("[[category:")  # MediaWiki accepts case-insensitive
    if cat_idx != -1:
        head = header if clear_existing_desc else text[:cat_idx]
        tail = text[cat_idx:]
        return head + new_block + "\n\n" + tail
    if clear_existing_desc:
        return header + new_block + "\n"
    return text.rstrip() + "\n\n" + new_block + "\n"


def _clear_template_desc(text: str, template_names: tuple[str, ...]) -> tuple[str, bool]:
    """Rewrite the `desc=...` value inside the first matching template
    invocation (e.g. `{{NWN:Spell|desc=...}}`) to the pointer stub. Leaves the
    rest of the page untouched.

    Returns `(new_text, did_clear)` so the caller can tell whether a template
    was actually rewritten (in which case the freeform-prose fallback is not
    needed)."""
    for name in template_names:
        open_idx = text.find("{{" + name)
        if open_idx == -1:
            continue
        close_after = _find_template_close(text, (name,))
        if close_after is None:
            continue
        block = text[open_idx:close_after]
        d_idx = block.find("|desc=")
        if d_idx == -1:
            return text, False
        rest = block[d_idx + len("|desc="):]
        end = _next_top_level_pipe_or_close(rest)
        # Surround the stub in newlines so trailing params (`|icon=...}}`) land
        # on their own line, keeping the template invocation legible.
        new_block_text = (block[:d_idx + len("|desc=")]
                          + "\n" + DESC_STUB + "\n"
                          + rest[end:])
        return text[:open_idx] + new_block_text + text[close_after:], True
    return text, False


def _next_top_level_pipe_or_close(s: str) -> int:
    """Return index in `s` of the next `|` or final `}}` that lives at template
    depth 0. Skips over any nested {{...}} templates within `desc=`."""
    depth = 0
    i = 0
    while i < len(s):
        two = s[i:i + 2]
        if two == "{{":
            depth += 1
            i += 2
            continue
        if two == "}}":
            if depth == 0:
                return i
            depth -= 1
            i += 2
            continue
        if s[i] == "|" and depth == 0:
            return i
        i += 1
    return len(s)


def _find_template_close(text: str, template_names: tuple[str, ...]) -> Optional[int]:
    """Return the position immediately after the closing `}}` of the first
    occurrence of any of the given template invocations. None if not found."""
    for name in template_names:
        needle = "{{" + name
        i = text.find(needle)
        if i == -1:
            continue
        # Walk forward, tracking brace depth, to find the matching `}}`.
        depth = 0
        j = i
        while j < len(text) - 1:
            two = text[j:j + 2]
            if two == "{{":
                depth += 1
                j += 2
            elif two == "}}":
                depth -= 1
                j += 2
                if depth == 0:
                    return j
            else:
                j += 1
    return None
