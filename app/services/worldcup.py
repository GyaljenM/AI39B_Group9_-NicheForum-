"""World Cup 2026 live-score services.

Two small, single-responsibility classes:

* ``WorldCupAPIClient`` — talks to the API-Football REST endpoint. It owns
  authentication and turns any network/HTTP problem into a single, predictable
  ``WorldCupAPIError`` so callers never have to know about ``requests``.

* ``MatchDataManager`` — sits in front of the client. It caches the raw JSON for
  a short window (to respect API rate limits) and parses the deeply-nested
  payload into a flat, template-friendly structure (team names, flags, the live
  minute, and goal counts).

When no API key is configured the manager degrades gracefully and serves a small
set of clearly-labelled sample fixtures, so the UI still renders during local
development.
"""

import os
import time

import requests


class WorldCupAPIError(Exception):
    """Raised when live data cannot be retrieved from the upstream API."""


class WorldCupAPIClient:
    """Authenticate against API-Football and fetch live World Cup fixtures."""

    BASE_URL = "https://v3.football.api-sports.io"
    FIXTURES_PATH = "/fixtures"

    def __init__(self, api_key=None, league=1, season=2026, timeout=10):
        # Key may come from the constructor (Flask config) or the environment.
        self.api_key = api_key or os.environ.get("API_FOOTBALL_KEY")
        self.league = league
        self.season = season
        self.timeout = timeout
        self._session = requests.Session()
        if self.api_key:
            self._session.headers.update({"x-apisports-key": self.api_key})

    @property
    def is_configured(self):
        """True when an API key is available to authenticate requests."""
        return bool(self.api_key)

    def fetch_live_fixtures(self):
        """Return the raw JSON payload for all live World Cup fixtures.

        Calls ``/fixtures?league=<league>&season=<season>&live=all``. Any
        timeout, connection drop, bad status code, or malformed body is
        converted into ``WorldCupAPIError`` so the caller can degrade cleanly.
        """
        if not self.is_configured:
            raise WorldCupAPIError("No API key configured (set API_FOOTBALL_KEY).")

        url = f"{self.BASE_URL}{self.FIXTURES_PATH}"
        params = {"league": self.league, "season": self.season, "live": "all"}
        try:
            response = self._session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
        except requests.exceptions.Timeout as exc:
            raise WorldCupAPIError("The football API timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise WorldCupAPIError("Could not reach the football API.") from exc
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            raise WorldCupAPIError(f"Football API returned HTTP {status}.") from exc
        except requests.exceptions.RequestException as exc:
            raise WorldCupAPIError(f"Unexpected football API error: {exc}") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise WorldCupAPIError("Football API returned invalid JSON.") from exc


class MatchDataManager:
    """Cache and parse live-match data on top of a ``WorldCupAPIClient``.

    Responsibilities:
      * Hold the last successful API response in memory for ``cache_ttl``
        seconds so repeated page polls don't burn through the rate limit.
      * Flatten the nested API JSON into a list of clean match dicts that the
        front-end can consume directly.
    """

    # API-Football "short" status codes that mean a match is currently in play.
    LIVE_STATUSES = {"1H", "2H", "ET", "BT", "P", "LIVE", "HT"}

    def __init__(self, api_key=None, cache_ttl=30, client=None):
        self.client = client or WorldCupAPIClient(api_key=api_key)
        self.cache_ttl = cache_ttl
        self._cache = None          # parsed result dict
        self._cached_at = 0.0       # monotonic timestamp of the last refresh

    def get_live_matches(self, force_refresh=False):
        """Return a parsed, cache-aware live-match payload.

        Shape::

            {
                "source": "live" | "sample" | "error",
                "matches": [ {clean match dict}, ... ],
                "count": <int>,
                "message": <str or None>,   # set on error / sample
            }

        Never raises: API problems are caught and reported via ``source`` and
        ``message`` so the route layer can always return JSON.
        """
        now = time.monotonic()
        if (
            not force_refresh
            and self._cache is not None
            and (now - self._cached_at) < self.cache_ttl
        ):
            return self._cache

        if not self.client.is_configured:
            result = {
                "source": "sample",
                "matches": self._sample_matches(),
                "message": "Showing sample data — set API_FOOTBALL_KEY for live scores.",
            }
        else:
            try:
                raw = self.client.fetch_live_fixtures()
                result = {
                    "source": "live",
                    "matches": self._parse(raw),
                    "message": None,
                }
            except WorldCupAPIError as exc:
                # On failure, keep serving the last good cache if we have one.
                if self._cache is not None:
                    return self._cache
                result = {"source": "error", "matches": [], "message": str(exc)}

        result["count"] = len(result["matches"])
        self._cache = result
        self._cached_at = now
        return result

    @staticmethod
    def _parse(raw):
        """Flatten API-Football's nested payload into clean match dicts.

        Extracts, per fixture: team names, flags/logos, the live minute, the
        short status, league round, and the live goal counts for each side.
        """
        matches = []
        for fixture in (raw or {}).get("response", []):
            fx = fixture.get("fixture", {}) or {}
            status = fx.get("status", {}) or {}
            teams = fixture.get("teams", {}) or {}
            home = teams.get("home", {}) or {}
            away = teams.get("away", {}) or {}
            goals = fixture.get("goals", {}) or {}
            league = fixture.get("league", {}) or {}

            matches.append({
                "id": fx.get("id"),
                "minute": status.get("elapsed"),
                "status": status.get("short"),
                "status_long": status.get("long"),
                "round": league.get("round"),
                "home": {
                    "name": home.get("name"),
                    "flag": home.get("logo"),
                    "goals": goals.get("home") or 0,
                },
                "away": {
                    "name": away.get("name"),
                    "flag": away.get("logo"),
                    "goals": goals.get("away") or 0,
                },
            })
        return matches

    @staticmethod
    def _sample_matches():
        """Clearly-labelled placeholder fixtures used when no key is set."""
        return [
            {
                "id": "sample-1",
                "minute": 67,
                "status": "2H",
                "status_long": "Second Half",
                "round": "Group Stage - 2 (sample)",
                "home": {"name": "Brazil", "flag": "https://media.api-sports.io/flags/br.svg", "goals": 2},
                "away": {"name": "Argentina", "flag": "https://media.api-sports.io/flags/ar.svg", "goals": 1},
            },
            {
                "id": "sample-2",
                "minute": 34,
                "status": "1H",
                "status_long": "First Half",
                "round": "Group Stage - 1 (sample)",
                "home": {"name": "France", "flag": "https://media.api-sports.io/flags/fr.svg", "goals": 0},
                "away": {"name": "Germany", "flag": "https://media.api-sports.io/flags/de.svg", "goals": 0},
            },
            {
                "id": "sample-3",
                "minute": 81,
                "status": "2H",
                "status_long": "Second Half",
                "round": "Group Stage - 3 (sample)",
                "home": {"name": "Mexico", "flag": "https://media.api-sports.io/flags/mx.svg", "goals": 1},
                "away": {"name": "USA", "flag": "https://media.api-sports.io/flags/us.svg", "goals": 3},
            },
        ]


# Process-wide singleton so the 30-second cache is shared across all requests
# (the dev server is single-process; one manager keeps one warm cache).
_manager = None


def get_match_manager(api_key=None, cache_ttl=30):
    """Return the shared MatchDataManager, creating it on first use."""
    global _manager
    if _manager is None:
        _manager = MatchDataManager(api_key=api_key, cache_ttl=cache_ttl)
    return _manager
