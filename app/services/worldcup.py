"""Live World Cup score services, backed by football-data.org (v4).

Two small, single-responsibility classes:

* ``WorldCupAPIClient`` — talks to the football-data.org REST endpoint. It owns
  authentication (the ``X-Auth-Token`` header) and turns any network/HTTP
  problem into a single, predictable ``WorldCupAPIError`` so callers never have
  to know about ``requests``.

* ``MatchDataManager`` — sits in front of the client. It caches the raw JSON for
  a short window (to respect the free-tier rate limit of 10 requests/minute) and
  parses football-data.org's payload into a flat, template-friendly structure:
  team names, crests, the score, the match status, the round/group, and a few
  page-level counters (how many matches are live, goals scored today).

The browser never calls football-data.org directly — it polls our own
``/api/live`` route, which calls this service server-side. That hides the token
and sidesteps the CORS block football-data.org applies to direct browser calls.

When no token is configured the manager degrades gracefully and serves a small
set of clearly-labelled sample fixtures, so the UI still renders during local
development.
"""

import os
import time
from datetime import datetime, timezone

import requests


class WorldCupAPIError(Exception):
    """Raised when live data cannot be retrieved from the upstream API."""


class WorldCupAPIClient:
    """Authenticate against football-data.org and fetch World Cup matches."""

    BASE_URL = "https://api.football-data.org/v4"

    def __init__(self, token=None, competition="WC", timeout=10):
        # Token may come from the constructor (Flask config) or the environment.
        # FOOTBALL_DATA_TOKEN is the canonical name; API_FOOTBALL_KEY is accepted
        # for backwards compatibility with older config.
        self.token = (
            token
            or os.environ.get("FOOTBALL_DATA_TOKEN")
            or os.environ.get("API_FOOTBALL_KEY")
        )
        self.competition = competition
        self.timeout = timeout
        # Last seen value of the free-tier rate-limit budget (requests left this
        # minute), parsed from the response headers football-data.org sends.
        self.requests_available = None
        self._session = requests.Session()
        if self.token:
            self._session.headers.update({"X-Auth-Token": self.token})

    @property
    def is_configured(self):
        """True when a token is available to authenticate requests."""
        return bool(self.token)

    def fetch_competition_matches(self):
        """Return the raw JSON payload for every match in the competition.

        Calls ``/competitions/<code>/matches`` (default code ``WC`` = FIFA World
        Cup). Returning the whole tournament in one call — then partitioning it
        in Python — keeps us to a single request per cache window, well under the
        free-tier rate limit. Any timeout, connection drop, bad status code, or
        malformed body is converted into ``WorldCupAPIError`` so the caller can
        degrade cleanly.
        """
        if not self.is_configured:
            raise WorldCupAPIError("No API token configured (set FOOTBALL_DATA_TOKEN).")

        url = f"{self.BASE_URL}/competitions/{self.competition}/matches"
        try:
            response = self._session.get(url, timeout=self.timeout)
        except requests.exceptions.Timeout as exc:
            raise WorldCupAPIError("The football API timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise WorldCupAPIError("Could not reach the football API.") from exc
        except requests.exceptions.RequestException as exc:
            raise WorldCupAPIError(f"Unexpected football API error: {exc}") from exc

        # football-data.org advertises the remaining per-minute budget in the
        # response headers (Daniel's email explicitly asks clients to watch these
        # for automatic throttling). Record it so callers can back off.
        self.requests_available = response.headers.get("X-Requests-Available-Minute")

        # 429 = rate limited. Surface the reset window so we can wait it out
        # instead of hammering the limiter further.
        if response.status_code == 429:
            reset = response.headers.get("X-RequestCounter-Reset") or response.headers.get("Retry-After") or "?"
            raise WorldCupAPIError(f"Rate limited by the football API — retry in {reset}s.")

        if response.status_code == 403:
            raise WorldCupAPIError(
                "Football API returned HTTP 403 — this token can't access the "
                "World Cup competition (check your football-data.org plan)."
            )

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            raise WorldCupAPIError(f"Football API returned HTTP {status}.") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise WorldCupAPIError("Football API returned invalid JSON.") from exc


class MatchDataManager:
    """Cache and parse World Cup match data on top of a ``WorldCupAPIClient``.

    Responsibilities:
      * Hold the last successful API response in memory for ``cache_ttl`` seconds
        so repeated page polls don't burn through the rate limit.
      * Flatten football-data.org's payload into clean match dicts and split them
        into what's live now, what's coming up, and recent results.
    """

    # football-data.org status codes (see their docs).
    LIVE_STATUSES = {"IN_PLAY", "PAUSED", "SUSPENDED"}
    FINISHED_STATUSES = {"FINISHED", "AWARDED"}
    UPCOMING_STATUSES = {"SCHEDULED", "TIMED"}

    def __init__(self, token=None, cache_ttl=30, client=None, competition="WC"):
        self.client = client or WorldCupAPIClient(token=token, competition=competition)
        self.cache_ttl = cache_ttl
        self._cache = None          # parsed result dict
        self._cached_at = 0.0       # monotonic timestamp of the last refresh

    def get_scoreboard(self, force_refresh=False):
        """Return a parsed, cache-aware scoreboard payload.

        Shape::

            {
                "source": "live" | "fixtures" | "sample" | "error",
                "message": <str or None>,        # context / error / sample note
                "competition": "FIFA World Cup",
                "live_count": <int>,             # matches in play right now
                "goals_today": <int>,            # goals across today's matches
                "matches": [ {clean match dict}, ... ],   # primary grid
                "upcoming": [ {clean match dict}, ... ],  # next kickoffs
                "updated": <ISO-8601 UTC string>,
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
            result = self._sample_payload()
        else:
            try:
                raw = self.client.fetch_competition_matches()
                result = self._build(raw)
            except WorldCupAPIError as exc:
                # On failure, keep serving the last good cache if we have one.
                if self._cache is not None:
                    return self._cache
                result = {
                    "source": "error",
                    "message": str(exc),
                    "competition": "FIFA World Cup",
                    "live_count": 0,
                    "goals_today": 0,
                    "matches": [],
                    "upcoming": [],
                    "updated": self._now_iso(),
                }

        self._cache = result
        self._cached_at = now
        return result

    # Backwards-compatible alias: the original API exposed get_live_matches().
    def get_live_matches(self, force_refresh=False):
        return self.get_scoreboard(force_refresh=force_refresh)

    def _build(self, raw):
        """Partition the raw payload and assemble the scoreboard dict."""
        competition = ((raw or {}).get("competition") or {}).get("name") or "FIFA World Cup"
        parsed = [self._parse_match(m) for m in (raw or {}).get("matches", [])]

        live = [m for m in parsed if m["status"] in self.LIVE_STATUSES]
        finished = [m for m in parsed if m["status"] in self.FINISHED_STATUSES]
        upcoming = [m for m in parsed if m["status"] in self.UPCOMING_STATUSES]

        finished.sort(key=lambda m: m["utc_date"] or "", reverse=True)
        upcoming.sort(key=lambda m: m["utc_date"] or "")

        if live:
            display = live
            source = "live"
            message = None
        elif upcoming:
            display = upcoming[:6]
            source = "fixtures"
            message = "No World Cup match is live right now — showing the next kickoffs."
        else:
            display = finished[:6]
            source = "fixtures"
            message = "No World Cup match is live right now — showing recent results."

        today = datetime.now(timezone.utc).date().isoformat()
        goals_today = sum(
            (m["home"]["goals"] or 0) + (m["away"]["goals"] or 0)
            for m in parsed
            if (m["utc_date"] or "").startswith(today)
            and m["status"] in (self.LIVE_STATUSES | self.FINISHED_STATUSES)
        )

        return {
            "source": source,
            "message": message,
            "competition": competition,
            "live_count": len(live),
            "goals_today": goals_today,
            "matches": display,
            "upcoming": upcoming[:6],
            "updated": self._now_iso(),
        }

    @staticmethod
    def _parse_match(m):
        """Flatten one football-data.org match into a clean, flat dict.

        v4 score shape: ``score.fullTime = {"home": <int|null>, "away": <int|null>}``.
        Teams expose ``name``, ``shortName``, ``tla`` and ``crest`` (image URL).
        """
        m = m or {}
        status = m.get("status")
        full = (m.get("score") or {}).get("fullTime") or {}
        home_team = m.get("homeTeam") or {}
        away_team = m.get("awayTeam") or {}
        stage = (m.get("stage") or "").replace("_", " ").title() or None

        return {
            "id": m.get("id"),
            "status": status,
            "is_live": status in MatchDataManager.LIVE_STATUSES,
            "utc_date": m.get("utcDate"),
            "stage": stage,
            "group": m.get("group"),
            "matchday": m.get("matchday"),
            "home": {
                "name": home_team.get("name") or home_team.get("shortName") or "TBD",
                "short": home_team.get("tla") or home_team.get("shortName"),
                "crest": home_team.get("crest"),
                "goals": full.get("home"),
            },
            "away": {
                "name": away_team.get("name") or away_team.get("shortName") or "TBD",
                "short": away_team.get("tla") or away_team.get("shortName"),
                "crest": away_team.get("crest"),
                "goals": full.get("away"),
            },
        }

    @staticmethod
    def _now_iso():
        """Current UTC time as an ISO-8601 string (``...Z``)."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _sample_payload(self):
        """Clearly-labelled placeholder scoreboard used when no token is set."""
        sample = [
            {
                "id": "sample-1",
                "status": "IN_PLAY",
                "is_live": True,
                "utc_date": self._now_iso(),
                "stage": "Group Stage",
                "group": "Group A",
                "matchday": 2,
                "home": {"name": "Brazil", "short": "BRA",
                         "crest": "https://crests.football-data.org/764.svg", "goals": 2},
                "away": {"name": "Argentina", "short": "ARG",
                         "crest": "https://crests.football-data.org/762.svg", "goals": 1},
            },
            {
                "id": "sample-2",
                "status": "PAUSED",
                "is_live": True,
                "utc_date": self._now_iso(),
                "stage": "Group Stage",
                "group": "Group C",
                "matchday": 1,
                "home": {"name": "France", "short": "FRA",
                         "crest": "https://crests.football-data.org/773.svg", "goals": 0},
                "away": {"name": "Germany", "short": "GER",
                         "crest": "https://crests.football-data.org/759.svg", "goals": 0},
            },
        ]
        return {
            "source": "sample",
            "message": "Showing sample data — set FOOTBALL_DATA_TOKEN for live scores.",
            "competition": "FIFA World Cup",
            "live_count": 2,
            "goals_today": 3,
            "matches": sample,
            "upcoming": [],
            "updated": self._now_iso(),
        }


# Process-wide singleton so the cache is shared across all requests (the dev
# server is single-process; one manager keeps one warm cache).
_manager = None


def get_match_manager(token=None, cache_ttl=30):
    """Return the shared MatchDataManager, creating it on first use."""
    global _manager
    if _manager is None:
        _manager = MatchDataManager(token=token, cache_ttl=cache_ttl)
    return _manager
