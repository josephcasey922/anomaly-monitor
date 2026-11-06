# Synthetic PostgreSQL demonstration (Docker required)

**Local synthetic demo only.** The example password strings are intentionally public and **must never** be reused for real data or exposed to the internet. Docker Compose binds port **5433** to **127.0.0.1** only.

## Start the database

From the repository root:

```powershell
docker compose up -d
.\.venv\Scripts\python.exe scripts/seed_postgres.py seed
```

The Compose `postgres_init.sql` file creates `public.daily_metrics` and a login `anomaly_reader` with `SELECT` but no table-write permissions.

## Connect in the interactive app

Run `anomaly-monitor app`, choose **PostgreSQL**, and enter:

| Field | Local demo value |
|---|---|
| Host | `localhost` |
| Port | `5433` |
| Database | `anomaly_demo` |
| Username | `anomaly_reader` |
| Password | `demo_reader_LOCAL_ONLY` |
| SSL mode | `prefer` (local demo) |
| Table | `public.daily_metrics` |

Choose **Discover accessible tables**, then **Preview table**, then map `BusinessDate`, `StoreID`, and the numerical metrics. Select `period` grain and daily frequency. Click **Run analysis**.

## Simulate records arriving

While the app remains running:

```powershell
.\.venv\Scripts\python.exe scripts/seed_postgres.py append
```

Use the app's **Run analysis** button again, or enable its **Automatically poll PostgreSQL** option to refresh reports on a selected interval (minimum 10 seconds). The demo script inserts data idempotently with `ON CONFLICT DO NOTHING`.

For an unattended terminal process, instead configure `examples/postgres_config.yaml` and set its password through the environment:

```powershell
$env:ANOMALY_MONITOR_DB_PASSWORD="demo_reader_LOCAL_ONLY"
.\.venv\Scripts\anomaly-monitor.exe run --config examples/postgres_config.yaml
.\.venv\Scripts\anomaly-monitor.exe watch --config examples/postgres_config.yaml --interval 60
```

## Important operational and security limits

- A real PostgreSQL connection was **not available in the package-build environment**. SQL reader logic has tests against SQLite with schema reflection and bounded access, but you should complete this Docker demo locally before claiming PostgreSQL has been tested end to end.
- Use a genuine read-only role for company systems, not an administrator account. The app has no arbitrary SQL textbox.
- Database credentials supplied in the Streamlit interface last only for the running browser session. Reusable YAML excludes passwords and uses `password_env` for CLI execution.
- The source is reread at a configured interval; this is **polling, not database triggers, CDC, or guaranteed instant detection**.
- Without a stable completeness cutoff, today's data may be partial; the calendar quality system flags incomplete periods but cannot know every store's business closure calendar or posting delay.
- `max_rows` prevents silent truncation. Restrict date range when tables exceed the selected hard cap; for larger data use a purpose-built approved reporting view or incremental ingestion in a later version.
- Use TLS (`require`/`verify-full` as applicable), secrets management, service accounts and audit logging before any production deployment.

Stop the local demo with `docker compose down`.
