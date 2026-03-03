from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import aiohttp

from src.models import JobPost, UserPreferences, ROLE_SYNONYMS
from src.providers.base import JobProvider

logger = logging.getLogger(__name__)

API_BASE = "https://api.adzuna.com/v1/api/jobs"


class AdzunaProvider(JobProvider):
    """Provider that fetches jobs from the Adzuna API (requires API credentials)."""

    def __init__(self, app_id: str, app_key: str, country: str = "il") -> None:
        """Initialise with Adzuna API credentials and target country.

        Examples:
            >>> p = AdzunaProvider("my_id", "my_key", "gb")
            >>> p._country
            'gb'

            >>> p = AdzunaProvider("id", "key")
            >>> p._country
            'il'  # default
        """
        self._app_id = app_id
        self._app_key = app_key
        self._country = country

    @property
    def name(self) -> str:
        """Return the provider identifier.

        Examples:
            >>> AdzunaProvider("id", "key").name
            'adzuna'

            >>> AdzunaProvider("id", "key").name == "adzuna"
            True
        """
        return "adzuna"

    async def search(self, preferences: UserPreferences) -> list[JobPost]:
        """Query the Adzuna search API with keywords derived from user roles.

        Returns an empty list when no keywords can be built (e.g. roles is
        ``["Other"]`` only).

        Examples:
            >>> prefs = UserPreferences(user_id=1, chat_id=1,
            ...     roles=["Data Engineer", "ML Engineer"])
            >>> jobs = await AdzunaProvider("id", "key", "il").search(prefs)
            >>> all(j.source == "adzuna" for j in jobs)
            True

            >>> prefs_other = UserPreferences(user_id=2, chat_id=2, roles=["Other"])
            >>> await AdzunaProvider("id", "key").search(prefs_other)
            []  # "Other" alone produces no keywords
        """
        keywords = _build_keywords(preferences)
        if not keywords:
            return []

        url = f"{API_BASE}/{self._country}/search/1"
        params = {
            "app_id": self._app_id,
            "app_key": self._app_key,
            "results_per_page": 50,
            "what": keywords,
            "content-type": "application/json",
        }

        all_jobs: list[JobPost] = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        logger.warning("Adzuna returned %s", resp.status)
                        return []
                    data = await resp.json()

            for item in data.get("results", []):
                post = _parse_job(item)
                if post:
                    all_jobs.append(post)

        except Exception:
            logger.exception("Error fetching from Adzuna")

        logger.info("Adzuna returned %d jobs", len(all_jobs))
        return all_jobs


def _build_keywords(prefs: UserPreferences) -> str:
    """Join user roles into an Adzuna ``what`` query using OR.

    "Other" is excluded since it has no meaningful keyword.

    Examples:
        >>> _build_keywords(UserPreferences(user_id=1, chat_id=1,
        ...     roles=["Backend Developer", "DevOps Engineer"]))
        'Backend Developer OR DevOps Engineer'

        >>> _build_keywords(UserPreferences(user_id=2, chat_id=2, roles=["Other"]))
        ''  # empty — caller should skip the API call
    """
    parts: list[str] = []
    for role in prefs.roles:
        if role == "Other":
            continue
        parts.append(role)
    return " OR ".join(parts)


def _parse_job(item: dict) -> JobPost | None:
    """Convert a raw Adzuna API result dict into a ``JobPost``, or ``None``.

    Examples:
        >>> _parse_job({"title": "QA Lead", "company": {"display_name": "TestCo"},
        ...             "location": {"display_name": "London"}, "id": 77,
        ...             "redirect_url": "https://adzuna.com/j/77"})
        JobPost(source='adzuna', job_id='77', title='QA Lead', company='TestCo', ...)

        >>> _parse_job({"title": "", "redirect_url": ""})
        None
    """
    title = item.get("title", "").strip()
    company = item.get("company", {}).get("display_name", "").strip()
    location = item.get("location", {}).get("display_name", "").strip()
    url = item.get("redirect_url", "").strip()

    if not title or not url:
        return None

    ext_id = item.get("id", "")
    job_id = str(ext_id) if ext_id else hashlib.md5(url.encode()).hexdigest()

    created = item.get("created")
    published_at = None
    if created:
        try:
            published_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    return JobPost(
        source="adzuna",
        job_id=job_id,
        title=title,
        company=company,
        location=location,
        url=url,
        remote=False,
        published_at=published_at,
    )
