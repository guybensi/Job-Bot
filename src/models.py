from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


AVAILABLE_ROLES: list[str] = [
    "Software Engineer",
    "Frontend Developer",
    "Backend Developer",
    "Full Stack Developer",
    "DevOps Engineer",
    "Data Scientist",
    "Data Engineer",
    "ML Engineer",
    "QA Engineer",
    "Product Manager",
    "UI/UX Designer",
    "Mobile Developer",
    "Cybersecurity",
    "System Administrator",
    "Other",
]

EXPERIENCE_OPTIONS: list[str] = [
    "0-1",
    "1-3",
    "3-5",
    "5-8",
    "8+",
]

LOCATION_OPTIONS: list[str] = [
    "South",
    "Center",
    "Tel Aviv",
    "Jerusalem",
    "North",
    "Remote-Only",
]

WORK_MODE_OPTIONS: list[str] = [
    "On-site",
    "Hybrid",
    "Remote",
]

ROLE_SYNONYMS: dict[str, list[str]] = {
    "Software Engineer": ["software engineer", "software developer", "swe"],
    "Frontend Developer": ["frontend", "front-end", "front end", "react", "vue", "angular"],
    "Backend Developer": ["backend", "back-end", "back end", "server-side"],
    "Full Stack Developer": ["full stack", "fullstack", "full-stack"],
    "DevOps Engineer": ["devops", "dev ops", "sre", "site reliability", "platform engineer"],
    "Data Scientist": ["data scientist", "data science"],
    "Data Engineer": ["data engineer", "data engineering", "etl"],
    "ML Engineer": ["machine learning", "ml engineer", "deep learning", "ai engineer"],
    "QA Engineer": ["qa", "quality assurance", "test engineer", "sdet"],
    "Product Manager": ["product manager", "product owner", "pm"],
    "UI/UX Designer": ["ui", "ux", "designer", "product designer"],
    "Mobile Developer": ["mobile", "ios", "android", "flutter", "react native"],
    "Cybersecurity": ["cyber", "security", "infosec", "penetration"],
    "System Administrator": ["sysadmin", "system admin", "it admin", "infrastructure"],
    "Other": [],
}


@dataclass
class UserPreferences:
    user_id: int
    chat_id: int
    roles: list[str] = field(default_factory=list)
    years_exp: str = ""
    locations: list[str] = field(default_factory=list)
    work_mode: str = ""
    is_paused: bool = False


@dataclass
class JobPost:
    source: str
    job_id: str
    title: str
    company: str
    location: str
    url: str
    remote: bool = False
    tags: list[str] = field(default_factory=list)
    published_at: datetime | None = None
