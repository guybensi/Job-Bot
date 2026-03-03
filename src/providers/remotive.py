from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import aiohttp

from src.models import JobPost, UserPreferences, ROLE_SYNONYMS
from src.providers.base import JobProvider

logger = logging.getLogger(__name__)

API_URL = "https://remotive.com/api/remote-jobs"

CATEGORY_MAP: dict[str, str] = {
    "Software Engineer": "software-dev",
    "Frontend Developer": "software-dev",
    "Backend Developer": "software-dev",
    "Full Stack Developer": "software-dev",
    "DevOps Engineer": "devops",
    "Data Scientist": "data",
    "Data Engineer": "data",
    "ML Engineer": "data",
    "QA Engineer": "qa",
    "Product Manager": "product",
    "UI/UX Designer": "design",
    "Mobile Developer": "software-dev",
    "Cybersecurity": "infosec",
    "System Administrator": "sys-admin",
}


class RemotiveProvider(JobProvider):
    """Provider that fetches remote jobs from the Remotive public API."""

    @property
    def name(self) -> str:
        """Return the provider identifier.

        Examples:
            >>> RemotiveProvider().name
            'remotive'

            >>> RemotiveProvider().name == "remotive"
            True
        """
        return "remotive"

    async def search(self, preferences: UserPreferences) -> list[JobPost]:
        """Fetch remote job listings from Remotive filtered by mapped categories.

        Maps user roles to Remotive's category slugs (e.g. "Software Engineer"
        → "software-dev"), fetches each category, then filters results by role
        keyword matching.

        Examples:
            >>> prefs = UserPreferences(user_id=1, chat_id=1,
            ...     roles=["DevOps Engineer"], locations=["Remote-Only"], work_mode="Remote")
            >>> jobs = await RemotiveProvider().search(prefs)
            >>> all(j.remote for j in jobs)
            True  # all Remotive jobs are remote

            >>> prefs2 = UserPreferences(user_id=2, chat_id=2, roles=["Other"])
            >>> jobs = await RemotiveProvider().search(prefs2)
            >>> len(jobs) >= 0
            True  # "Other" matches all titles
        """
        categories = set()
        for role in preferences.roles:
            cat = CATEGORY_MAP.get(role)
            if cat:
                categories.add(cat)

        if not categories:
            categories.add("software-dev")

        all_jobs: list[JobPost] = []
        try:
            async with aiohttp.ClientSession() as session:
                for category in categories:
                    params = {"category": category, "limit": 50}
                    async with session.get(
                        API_URL,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status != 200:
                            logger.warning("Remotive returned %s for category %s", resp.status, category)
                            continue
                        data = await resp.json()

                    for item in data.get("jobs", []):
                        post = _parse_job(item)
                        if post and _role_matches(post, preferences):
                            all_jobs.append(post)

        except Exception:
            logger.exception("Error fetching from Remotive")

        logger.info("Remotive returned %d matching jobs", len(all_jobs))
        return all_jobs


def _parse_job(item: dict) -> JobPost | None:
    """Convert a raw Remotive API dict into a ``JobPost``, or ``None`` if invalid.

    All Remotive jobs are treated as remote.

    Examples:
        >>> _parse_job({"title": "ML Engineer", "company_name": "DeepCo", "id": 555,
        ...             "candidate_required_location": "Worldwide",
        ...             "url": "https://remotive.com/j/555", "tags": ["python", "ml"]})
        JobPost(source='remotive', job_id='555', title='ML Engineer', remote=True, ...)

        >>> _parse_job({"title": "", "url": ""})
        None
    """
    title = item.get("title", "").strip()
    company = item.get("company_name", "").strip()
    location = item.get("candidate_required_location", "").strip()
    url = item.get("url", "").strip()

    if not title or not url:
        return None

    ext_id = item.get("id", "")
    job_id = str(ext_id) if ext_id else hashlib.md5(url.encode()).hexdigest()

    tags = item.get("tags", []) or []

    pub_date = item.get("publication_date")
    published_at = None
    if pub_date:
        try:
            published_at = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    return JobPost(
        source="remotive",
        job_id=job_id,
        title=title,
        company=company,
        location=location or "Remote",
        url=url,
        remote=True,
        tags=[str(t) for t in tags],
        published_at=published_at,
    )


def _role_matches(job: JobPost, prefs: UserPreferences) -> bool:
    """Check if the job title or tags contain any synonym for the user's roles.

    Selecting "Other" always matches.

    Examples:
        >>> job = JobPost(source="remotive", job_id="1", title="Senior DevOps Engineer",
        ...               company="X", location="Remote", url="u", remote=True)
        >>> _role_matches(job, UserPreferences(user_id=1, chat_id=1, roles=["DevOps Engineer"]))
        True  # "devops" is a synonym

        >>> _role_matches(job, UserPreferences(user_id=2, chat_id=2, roles=["UI/UX Designer"]))
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
