from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import aiohttp

from src.models import (
    JobPost,
    UserPreferences,
    ROLE_SYNONYMS,
    SENIOR_TITLE_KEYWORDS,
    JUNIOR_EXPERIENCE_RANGES,
    ISRAEL_LOCATION_KEYWORDS,
)
from src.providers.base import JobProvider

logger = logging.getLogger(__name__)

API_URL = "https://www.arbeitnow.com/api/job-board-api"
MAX_PAGES = 3


class ArbeitnowProvider(JobProvider):
    """Provider that fetches jobs from the Arbeitnow public API (no key required)."""

    @property
    def name(self) -> str:
        """Return the provider identifier.

        Examples:
            >>> ArbeitnowProvider().name
            'arbeitnow'

            >>> ArbeitnowProvider().name == "arbeitnow"
            True
        """
        return "arbeitnow"

    async def search(self, preferences: UserPreferences) -> list[JobPost]:
        """Fetch job listings from Arbeitnow and filter by user preferences.

        Paginates up to ``MAX_PAGES`` pages, parses each listing, and keeps
        only those matching role / location / work-mode criteria.

        Examples:
            >>> prefs = UserPreferences(user_id=1, chat_id=1,
            ...     roles=["Frontend Developer"], locations=["Remote-Only"], work_mode="Remote")
            >>> jobs = await ArbeitnowProvider().search(prefs)
            >>> all(j.source == "arbeitnow" for j in jobs)
            True

            >>> prefs_no_match = UserPreferences(user_id=2, chat_id=2,
            ...     roles=["Cybersecurity"], locations=["South"], work_mode="On-site")
            >>> jobs = await ArbeitnowProvider().search(prefs_no_match)
            >>> len(jobs)  # may be 0 if no cybersecurity jobs in South Israel
            0
        """
        all_jobs: list[JobPost] = []

        try:
            async with aiohttp.ClientSession() as session:
                for page in range(1, MAX_PAGES + 1):
                    url = f"{API_URL}?page={page}"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status != 200:
                            logger.warning("Arbeitnow returned %s on page %d", resp.status, page)
                            break
                        data = await resp.json()

                    jobs = data.get("data", [])
                    if not jobs:
                        break

                    for item in jobs:
                        post = _parse_job(item)
                        if post and _matches(post, preferences):
                            all_jobs.append(post)

        except Exception:
            logger.exception("Error fetching from Arbeitnow")

        logger.info("Arbeitnow returned %d matching jobs", len(all_jobs))
        return all_jobs


def _parse_job(item: dict) -> JobPost | None:
    """Convert a raw Arbeitnow API dict into a ``JobPost``, or ``None`` if invalid.

    Examples:
        >>> _parse_job({"title": "Senior SWE", "company_name": "Acme",
        ...             "location": "Berlin", "url": "https://acme.com/j/1",
        ...             "slug": "senior-swe", "remote": True, "tags": ["python"]})
        JobPost(source='arbeitnow', job_id='senior-swe', title='Senior SWE', ...)

        >>> _parse_job({"title": "", "url": ""})
        None  # missing required fields
    """
    title = item.get("title", "").strip()
    company = item.get("company_name", "").strip()
    location = item.get("location", "").strip()
    url = item.get("url", "").strip()

    if not title or not url:
        return None

    slug = item.get("slug", "")
    job_id = slug or hashlib.md5(url.encode()).hexdigest()

    remote = item.get("remote", False)
    tags = item.get("tags", []) or []

    created = item.get("created_at")
    published_at = None
    if created:
        try:
            published_at = datetime.fromtimestamp(created, tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            pass

    return JobPost(
        source="arbeitnow",
        job_id=job_id,
        title=title,
        company=company,
        location=location,
        url=url,
        remote=remote,
        tags=[str(t) for t in tags],
        published_at=published_at,
    )


def _matches(job: JobPost, prefs: UserPreferences) -> bool:
    """Return True if the job passes all three filters: role, location, and mode.

    Examples:
        >>> job = JobPost(source="arbeitnow", job_id="1", title="Backend Developer",
        ...               company="X", location="Tel Aviv", url="u", remote=False)
        >>> prefs = UserPreferences(user_id=1, chat_id=1,
        ...     roles=["Backend Developer"], locations=["Tel Aviv"], work_mode="On-site")
        >>> _matches(job, prefs)
        True

        >>> prefs2 = UserPreferences(user_id=2, chat_id=2,
        ...     roles=["Data Scientist"], locations=["North"], work_mode="Remote")
        >>> _matches(job, prefs2)
        False  # role and location don't match
    """
    if not _role_matches(job, prefs):
        return False
    if not _experience_matches(job, prefs):
        return False
    if not _location_matches(job, prefs):
        return False
    if not _mode_matches(job, prefs):
        return False
    return True


def _role_matches(job: JobPost, prefs: UserPreferences) -> bool:
    """Check if the job title or tags contain any synonym for the user's roles.

    Selecting "Other" always matches.

    Examples:
        >>> job = JobPost(source="a", job_id="1", title="React Frontend Engineer",
        ...               company="X", location="", url="u")
        >>> prefs = UserPreferences(user_id=1, chat_id=1, roles=["Frontend Developer"])
        >>> _role_matches(job, prefs)
        True  # "react" and "frontend" are synonyms

        >>> prefs2 = UserPreferences(user_id=2, chat_id=2, roles=["Data Scientist"])
        >>> _role_matches(job, prefs2)
        False
    """
    if "Other" in prefs.roles:
        return True

    title_lower = job.title.lower()
    tags_lower = " ".join(job.tags).lower()
    text = f"{title_lower} {tags_lower}"

    for role in prefs.roles:
        synonyms = ROLE_SYNONYMS.get(role, [role.lower()])
        if not synonyms:
            synonyms = [role.lower()]
        for syn in synonyms:
            if syn in text:
                return True
    return False


def _experience_matches(job: JobPost, prefs: UserPreferences) -> bool:
    """Reject senior-level titles when the user has junior-level experience.

    Users with "0-1" or "1-3" years will not see jobs whose title contains
    words like "Senior", "Staff", "Lead", "Principal", etc.

    Examples:
        >>> job = JobPost(source="a", job_id="1", title="Senior Backend Developer",
        ...               company="X", location="", url="u")
        >>> _experience_matches(job, UserPreferences(user_id=1, chat_id=1, years_exp="0-1"))
        False

        >>> _experience_matches(job, UserPreferences(user_id=2, chat_id=2, years_exp="5-8"))
        True  # experienced user — no filtering
    """
    if prefs.years_exp not in JUNIOR_EXPERIENCE_RANGES:
        return True

    title_lower = job.title.lower()
    for keyword in SENIOR_TITLE_KEYWORDS:
        if keyword in title_lower:
            return False
    return True


def _location_matches(job: JobPost, prefs: UserPreferences) -> bool:
    """Check that the job is located in Israel or is a remote position.

    Only jobs whose location field contains an Israeli city name, "israel",
    or that are flagged remote (when the user wants remote) pass through.

    Examples:
        >>> job = JobPost(source="a", job_id="1", title="SWE", company="X",
        ...               location="Tel Aviv, Israel", url="u", remote=False)
        >>> prefs = UserPreferences(user_id=1, chat_id=1, locations=["Tel Aviv"])
        >>> _location_matches(job, prefs)
        True

        >>> job2 = JobPost(source="a", job_id="2", title="SWE", company="X",
        ...                location="New York, US", url="u", remote=False)
        >>> _location_matches(job2, prefs)
        False  # not in Israel
    """
    if "Remote-Only" in prefs.locations and job.remote:
        return True

    loc_lower = job.location.lower()

    if not any(kw in loc_lower for kw in ISRAEL_LOCATION_KEYWORDS):
        return False

    non_remote_locs = [l for l in prefs.locations if l != "Remote-Only"]
    if not non_remote_locs:
        return True

    for pref_loc in non_remote_locs:
        if pref_loc.lower() in loc_lower:
            return True

    return True


def _mode_matches(job: JobPost, prefs: UserPreferences) -> bool:
    """Check if the job's remote flag is compatible with the user's work mode.

    "Remote" and "Hybrid" accept any job. "On-site" rejects remote-only jobs.

    Examples:
        >>> job = JobPost(source="a", job_id="1", title="SWE", company="X",
        ...               location="Berlin", url="u", remote=True)
        >>> _mode_matches(job, UserPreferences(user_id=1, chat_id=1, work_mode="Remote"))
        True

        >>> _mode_matches(job, UserPreferences(user_id=2, chat_id=2, work_mode="On-site"))
        False  # remote job excluded for on-site preference
    """
    if not prefs.work_mode or prefs.work_mode == "Remote":
        return True
    if prefs.work_mode == "On-site" and job.remote:
        return False
    return True
