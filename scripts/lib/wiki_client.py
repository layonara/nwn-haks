"""Minimal MediaWiki client for the wiki-sync pipeline.

Bot login + parse-wikitext GET + edit POST with throttling, bot-flag, and
maxlag retry. Designed for a single sync run; not a general-purpose library.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class WikiCreds:
    api_url: str
    username: str
    password: str


class WikiClient:
    def __init__(self, creds: WikiCreds, throttle_seconds: float = 1.0,
                 user_agent: str = "layonara-wiki-sync/1.0 (https://github.com/Layonara/nwn-haks)"):
        self._creds = creds
        self._session = requests.Session()
        self._session.headers["User-Agent"] = user_agent
        self._throttle = throttle_seconds
        self._csrf: str | None = None
        self._last_edit_at: float = 0.0
        self._logged_in = False

    # --- auth ---

    def login(self) -> None:
        r = self._session.get(self._creds.api_url, params={
            "action": "query", "meta": "tokens", "type": "login", "format": "json",
        }, timeout=20)
        r.raise_for_status()
        login_token = r.json()["query"]["tokens"]["logintoken"]

        r = self._session.post(self._creds.api_url, data={
            "action": "login",
            "lgname": self._creds.username,
            "lgpassword": self._creds.password,
            "lgtoken": login_token,
            "format": "json",
        }, timeout=20)
        r.raise_for_status()
        result = r.json().get("login", {}).get("result")
        if result != "Success":
            raise RuntimeError(f"wiki login failed: {r.json()}")
        self._logged_in = True

        r = self._session.get(self._creds.api_url, params={
            "action": "query", "meta": "tokens", "format": "json",
        }, timeout=20)
        r.raise_for_status()
        self._csrf = r.json()["query"]["tokens"]["csrftoken"]

    # --- read ---

    def list_image_files(self, prefixes: list[str]) -> set[str]:
        """Return the lowercase filenames of every uploaded File: page whose
        title starts with any of `prefixes` (case-insensitive). Used so the
        autosync renderer can degrade missing icons to plain text instead of
        broken-image links. Single anonymous query; no login required."""
        out: set[str] = set()
        for raw in prefixes:
            prefix = raw.lower()
            cont: dict | None = {}
            while cont is not None:
                params = {
                    "action": "query", "list": "allimages",
                    "aiprefix": prefix,  # MW normalises first letter on its own
                    "ailimit": "500", "format": "json",
                }
                if cont:
                    params.update(cont)
                r = self._session.get(self._creds.api_url, params=params, timeout=20)
                r.raise_for_status()
                payload = r.json()
                for img in payload.get("query", {}).get("allimages", []):
                    # img["name"] is e.g. "Is acidfog.png" (spaces, capitalised first letter)
                    out.add(img["name"].replace(" ", "_").lower())
                cont = payload.get("continue") or None
        return out

    def get_wikitext(self, title: str) -> str | None:
        """Return wikitext or None if the page doesn't exist."""
        r = self._session.get(self._creds.api_url, params={
            "action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
            "titles": title, "formatversion": "2", "format": "json",
        }, timeout=20)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", [])
        if not pages:
            return None
        page = pages[0]
        if page.get("missing"):
            return None
        revs = page.get("revisions", [])
        if not revs:
            return None
        return revs[0].get("slots", {}).get("main", {}).get("content", "")

    # --- write ---

    def edit(self, title: str, text: str, summary: str, *, bot: bool = True,
             create_only: bool = False, no_create: bool = False) -> dict:
        if not self._logged_in or not self._csrf:
            raise RuntimeError("must call login() before edit()")
        # client-side throttle
        wait = self._throttle - (time.monotonic() - self._last_edit_at)
        if wait > 0:
            time.sleep(wait)

        params = {
            "action": "edit",
            "title": title,
            "text": text,
            "summary": summary,
            "token": self._csrf,
            "format": "json",
            "maxlag": "5",
        }
        if bot:
            params["bot"] = "1"
        if create_only:
            params["createonly"] = "1"
        if no_create:
            params["nocreate"] = "1"

        for attempt in range(5):
            r = self._session.post(self._creds.api_url, data=params, timeout=30)
            self._last_edit_at = time.monotonic()
            try:
                payload = r.json()
            except ValueError:
                logger.error("non-JSON response: %s", r.text[:200])
                raise
            err = payload.get("error")
            if err and err.get("code") == "maxlag":
                lag = float(err.get("lag", 5))
                logger.warning("maxlag %.1fs, sleeping...", lag)
                time.sleep(min(30, lag + 1))
                continue
            if err and err.get("code") == "ratelimited":
                logger.warning("ratelimited, sleeping 30s...")
                time.sleep(30)
                continue
            if err:
                raise RuntimeError(f"edit failed: {err}")
            return payload.get("edit", {})
        raise RuntimeError("edit failed after 5 retries (maxlag/ratelimited)")
