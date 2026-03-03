from __future__ import annotations

from src.config import Config
from src.providers.base import JobProvider
from src.providers.arbeitnow import ArbeitnowProvider
from src.providers.remotive import RemotiveProvider
from src.providers.adzuna import AdzunaProvider


def get_enabled_providers(config: Config) -> list[JobProvider]:
    """Return a list of provider instances enabled by the current config.

    Examples:
        >>> cfg = Config(telegram_bot_token="t", arbeitnow_enabled=True,
        ...              remotive_enabled=False)
        >>> [p.name for p in get_enabled_providers(cfg)]
        ['arbeitnow']

        >>> cfg = Config(telegram_bot_token="t", arbeitnow_enabled=True,
        ...              remotive_enabled=True, adzuna_app_id="id", adzuna_app_key="key")
        >>> [p.name for p in get_enabled_providers(cfg)]
        ['arbeitnow', 'remotive', 'adzuna']
    """
    providers: list[JobProvider] = []

    if config.arbeitnow_enabled:
        providers.append(ArbeitnowProvider())

    if config.remotive_enabled:
        providers.append(RemotiveProvider())

    if config.adzuna_enabled:
        providers.append(AdzunaProvider(config.adzuna_app_id, config.adzuna_app_key, config.adzuna_country))

    return providers
