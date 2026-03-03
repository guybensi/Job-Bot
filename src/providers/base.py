from __future__ import annotations

from abc import ABC, abstractmethod

from src.models import JobPost, UserPreferences


class JobProvider(ABC):
    """Abstract base class for all job-search providers.

    Subclasses must implement ``name`` (a short identifier) and ``search``
    (the async method that queries the external API).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short unique identifier for the provider (e.g. ``"arbeitnow"``).

        Examples:
            >>> ArbeitnowProvider().name
            'arbeitnow'

            >>> RemotiveProvider().name
            'remotive'
        """
        ...

    @abstractmethod
    async def search(self, preferences: UserPreferences) -> list[JobPost]:
        """Query the external source and return matching job posts.

        Examples:
            >>> prefs = UserPreferences(user_id=1, chat_id=1,
            ...     roles=["Backend Developer"], locations=["Remote-Only"], work_mode="Remote")
            >>> jobs = await provider.search(prefs)
            >>> isinstance(jobs, list)
            True

            >>> prefs_empty = UserPreferences(user_id=2, chat_id=2)
            >>> await provider.search(prefs_empty)
            []  # no roles → no matches
        """
        ...
