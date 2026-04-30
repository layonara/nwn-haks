"""Minimal MediaWiki client for the wiki-sync pipeline.

Reads via the public action=query API (no auth needed; works from anywhere).
Writes go through one of two backends:

  * `DockerExecBackend` (default, used in CI/leanthar): shells out to
    `docker exec <wiki-container> php maintenance/edit.php`. No API password,
    just sudo+docker access. This is the same path the aragen Discord bot
    uses for changelogs and was chosen because the bot password in Coolify
    is stale (`messagecode: wrongpassword`) -- nobody noticed because the
    changelog cog also uses docker exec. See layonara-architecture.mdc for
    the full backstory.

  * `ApiBackend`: classic MediaWiki BotPasswords login + action=edit. Only
    useful if/when somebody refreshes the bot password at
    https://wiki.layonara.com/Special:BotPasswords and updates the
    WIKI_BOT_USER + WIKI_BOT_PASSWORD env vars. Throttle/maxlag/ratelimit
    retry logic is here for that future.

Either backend exposes a single `edit(title, text, summary)` method;
`WikiClient` picks one at construction time and the rest of the pipeline
doesn't care which.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class WikiCreds:
    api_url: str
    username: str
    password: str


@dataclass
class DockerExecBackend:
    """Edit pages by shelling into the wiki container's maintenance/edit.php.

    Set `ssh_host` to proxy through ssh (e.g. when running from a workstation
    that can't talk to the docker daemon directly); leave empty to assume the
    docker daemon is reachable locally (e.g. on leanthar itself).
    """
    container: str
    user: str = "Orth"
    ssh_host: str = ""

    def edit(self, title: str, text: str, summary: str) -> dict:
        cmd = ["docker", "exec", "-i", self.container,
               "php", "/var/www/html/maintenance/edit.php",
               "--user", self.user, "--summary", summary, title]
        if self.ssh_host:
            shell_cmd = " ".join(subprocess.list2cmdline([c]) for c in cmd)
            cmd = ["ssh", self.ssh_host, shell_cmd]
        proc = subprocess.run(cmd, input=text, text=True,
                              capture_output=True, timeout=60, check=False)
        if proc.returncode != 0:
            raise RuntimeError(
                f"edit.php failed (rc={proc.returncode}): "
                f"stdout={proc.stdout[-500:]} stderr={proc.stderr[-500:]}")
        return {"backend": "docker-exec", "stdout": proc.stdout[-200:]}


def make_default_backend() -> DockerExecBackend | None:
    """Build a DockerExecBackend from env vars, or return None if missing."""
    container = os.environ.get("WIKI_CONTAINER", "")
    if not container:
        return None
    return DockerExecBackend(
        container=container,
        user=os.environ.get("WIKI_BOT_USER", "Orth"),
        ssh_host=os.environ.get("WIKI_SSH_HOST", ""),
    )


class WikiClient:
    def __init__(self, creds: WikiCreds,
                 write_backend: DockerExecBackend | None = None,
                 throttle_seconds: float = 1.0,
                 user_agent: str = "layonara-wiki-sync/1.0 (https://github.com/Layonara/nwn-haks)"):
        self._creds = creds
        self._session = requests.Session()
        self._session.headers["User-Agent"] = user_agent
        self._throttle = throttle_seconds
        self._csrf: str | None = None
        self._last_edit_at: float = 0.0
        self._logged_in = False
        self._write_backend = write_backend

    @property
    def write_backend_name(self) -> str:
        if self._write_backend is not None:
            return f"docker-exec ({self._write_backend.container})"
        return "api"

    # --- auth (only needed when no docker-exec backend is configured) ---

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
        if self._write_backend is not None:
            return self._write_backend.edit(title, text, summary)
        if not self._logged_in or not self._csrf:
            raise RuntimeError(
                "no write backend configured: either set WIKI_CONTAINER for "
                "docker-exec mode or call login() first for API mode")
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
