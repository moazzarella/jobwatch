# jobwatch

Checks **Freelancer.com** and **Mostaql** every 15 minutes for new iOS, Flutter, mobile, WordPress and front-end jobs, and sends each new match to your Telegram.

- Freelancer.com: official public API (no login).
- Mostaql: public project listing pages (no login).
- Each job is sent once. The first run only says "now watching" so you aren't flooded with old jobs.
- If a source fails 3 runs in a row (blocked, site changed), you get one ⚠️ alert on Telegram, and a ✅ when it recovers.

## Change what it looks for
Edit `config.json`: `include` words (a job must contain one), `exclude` words (skip if it contains one), `max_bids` (skip crowded jobs).

## Where it runs
- **GitHub Actions** (`.github/workflows/jobwatch.yml`): every 15 min, 24/7. Needs repo secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Optional repo variable `JOBWATCH_SOURCES` (default `freelancer,mostaql`).
- **Mac** (`mac/install.sh`): for any site that blocks GitHub's servers. Runs every 15 min while the Mac is awake:
  `bash mac/install.sh <BOT_TOKEN> <CHAT_ID> mostaql`

Give each site to only one runner, or you'll get duplicates.

## Test locally without sending anything
`JOBWATCH_DRY_RUN=1 python3 jobwatch.py`
