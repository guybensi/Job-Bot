# Job-Bot

A Telegram bot that searches public job boards and sends you matching alerts every 2 hours.

## Features

- **Onboarding flow** — multi-select job roles, years of experience, preferred locations, and work mode via inline keyboards.
- **Pluggable providers** — ships with Arbeitnow (no key needed), Remotive, and optional Adzuna support.
- **Deduplication** — SQLite-backed seen-jobs table ensures you never receive the same listing twice.
- **User commands** — `/now` for an instant search, `/pause` / `/resume` to control alerts, `/preferences` to view or edit.
- **Scheduled searches** — APScheduler runs every 2 hours in the background.

## Quick Start

### 1. Create a Telegram Bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Send `/newbot`, follow the prompts, and copy the **bot token**.

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and paste your token:

```
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
```

### 3. Install Dependencies

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Run

```bash
python -m src.bot
```

The bot will start polling for messages and schedule job searches every 2 hours.

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Begin onboarding — set your job preferences |
| `/preferences` | View or edit your saved preferences |
| `/now` | Run an immediate job search |
| `/pause` | Pause scheduled alerts |
| `/resume` | Resume scheduled alerts |
| `/help` | Show available commands |

## Job Providers

### Arbeitnow (enabled by default)

Free public API — no API key required. Returns tech job listings from major ATS platforms (Greenhouse, SmartRecruiters, etc.). Covers Europe and remote positions.

### Remotive (enabled by default)

Free API for remote job listings. Filterable by category.

### Adzuna (optional)

Aggregates jobs from multiple boards. Requires a free API key:

1. Sign up at [developer.adzuna.com](https://developer.adzuna.com/).
2. Add to `.env`:
   ```
   ADZUNA_APP_ID=your_app_id
   ADZUNA_APP_KEY=your_app_key
   ADZUNA_COUNTRY=il
   ```

### LinkedIn / Glassdoor

**Not implemented.** Scraping these sites violates their Terms of Service. If you have access to LinkedIn's official Job Posting API or Glassdoor's partner API, you can implement a provider by extending `src/providers/base.py`.

## Adding a Custom Provider

1. Create a new file in `src/providers/`, e.g. `my_board.py`.
2. Subclass `JobProvider` from `src/providers/base.py`.
3. Implement the `search(preferences)` method returning a list of `JobPost`.
4. Register it in `src/providers/__init__.py`.

## Project Structure

```
src/
  bot.py            # Entry point, logging, application wiring
  __main__.py       # Enables `python -m src.bot`
  config.py         # Environment variable loader
  models.py         # UserPreferences, JobPost dataclasses
  db.py             # Async SQLite operations
  scheduler.py      # APScheduler job search loop
  handlers/
    start.py        # /start onboarding conversation
    preferences.py  # /preferences command
    commands.py     # /now, /pause, /resume, /help
  providers/
    base.py         # Abstract JobProvider interface
    arbeitnow.py    # Arbeitnow public API
    remotive.py     # Remotive API
    adzuna.py       # Adzuna API (optional)
    linkedin.py     # Stub — ToS restriction
    glassdoor.py    # Stub — ToS restriction
```

## Configuration Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from BotFather |
| `ARBEITNOW_ENABLED` | No | `true` | Enable Arbeitnow provider |
| `REMOTIVE_ENABLED` | No | `true` | Enable Remotive provider |
| `ADZUNA_APP_ID` | No | — | Adzuna API app ID |
| `ADZUNA_APP_KEY` | No | — | Adzuna API app key |
| `ADZUNA_COUNTRY` | No | `il` | Adzuna country code |
| `SEARCH_INTERVAL_HOURS` | No | `2` | Hours between scheduled searches |
| `LOG_LEVEL` | No | `INFO` | Python logging level |

## License

MIT
