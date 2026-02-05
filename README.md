# 4Site Calendar Analytics

Analyze your Google Calendar to understand meeting patterns, time allocation, and participant breakdowns. Available as both a CLI tool and a local web dashboard.

## Features

- **Meeting counts** by month, quarter, year, and week
- **Time breakdown** -- total hours in meetings, average duration, per-day averages
- **Internal vs Client vs External** classification based on email domains and event titles
- **Participant tracking** -- who you meet with most and for how long
- **Client breakdown** -- time spent per client
- **Day-of-week / duration patterns** -- when and how long your meetings are
- **Recurring vs one-off** analysis
- **Busiest days** ranking

### Data Sources

| Source | Flag | Setup Required |
|--------|------|---------------|
| Google Calendar API | _(default)_ | OAuth credentials |
| iCal file (.ics) | `--ical-file` | None |
| iCal URL | `--ical-url` | None |

### Interfaces

- **CLI** (`analyze.py`) -- Rich terminal tables and charts
- **Web Dashboard** (`web_server.py`) -- Local HTML GUI with interactive Chart.js charts

## Privacy

**No calendar data is stored to disk.** All event data is processed in memory and discarded when the program exits. Exported reports (JSON/CSV) contain only aggregate statistics with PII stripped.

The only file persisted is `token.json` (Google OAuth token) which you can delete at any time to revoke access.

## Quick Start

### 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure (optional)

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` to set your company's email domains and known client domains:

```yaml
company_domains:
  - "4sitestudios.com"

client_domains:
  "clienta.org": "Client A"
  "bignonprofit.org": "Big Nonprofit"
```

### 3a. Run the CLI

```bash
# Analyze an .ics file (no Google setup needed)
python analyze.py --ical-file my_calendar.ics

# Analyze from an iCal URL
python analyze.py --ical-url "https://calendar.google.com/calendar/ical/.../basic.ics"

# Use Google Calendar API (requires credentials.json -- see below)
python analyze.py

# Specific date range
python analyze.py --start 2025-01-01 --end 2025-12-31

# Quarterly breakdown
python analyze.py --period quarter

# Export
python analyze.py --export-csv report.csv --export-json report.json
```

#### CLI Subcommands

```bash
python analyze.py summary          # Summary stats only
python analyze.py breakdown --period quarter
python analyze.py types            # Meeting type breakdown
python analyze.py participants     # Top participants
python analyze.py clients          # Client time breakdown
python analyze.py schedule         # Day-of-week and duration patterns
```

### 3b. Run the Web Dashboard

```bash
python web_server.py
# Open http://127.0.0.1:5000 in your browser
```

Upload an `.ics` file or paste an iCal URL directly in the browser. No Google API setup required for file/URL mode.

## Google Calendar API Setup (Optional)

Only needed if you want to pull directly from Google Calendar:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable the **Google Calendar API**
4. Go to **Credentials** > **Create Credentials** > **OAuth 2.0 Client ID**
   - Application type: **Desktop application**
5. Download the JSON file and save as `credentials.json` in the project root
6. On first run, a browser window will open for authorization

### Exporting Your Google Calendar as .ics

If you prefer not to set up API credentials:

1. Open [Google Calendar](https://calendar.google.com)
2. Click the gear icon > **Settings**
3. Under your calendar, find **Integrate calendar**
4. Copy the **Secret address in iCal format**
5. Use it with: `python analyze.py --ical-url "YOUR_URL"`

## How Classification Works

Meetings are classified in this priority order:

1. **Solo** -- No attendees besides yourself
2. **Internal** -- All attendees share a `company_domains` email domain
3. **Client** -- Any attendee has a `client_domains` email, OR the title contains `client_title_keywords`
4. **External** -- Attendees from unknown domains

Configure these in `config.yaml` to match your organization.

## Project Structure

```
.
├── analyze.py                  # CLI entry point
├── web_server.py               # Web dashboard entry point
├── config.example.yaml         # Example configuration
├── requirements.txt
├── cal_analyzer/
│   ├── __init__.py
│   ├── auth.py                 # Google Calendar OAuth
│   ├── fetcher.py              # Google Calendar API data fetching
│   ├── ical_import.py          # iCal file/URL import
│   ├── classifier.py           # Internal/client/external classification
│   ├── analyzer.py             # Analytics engine
│   ├── config.py               # Configuration loader
│   ├── reporter.py             # Rich CLI output and CSV/JSON export
│   └── web/
│       ├── __init__.py
│       ├── app.py              # Flask web application
│       └── templates/
│           └── dashboard.html  # Interactive dashboard with Chart.js
```

## Deleting Stored Credentials

To revoke Google API access and remove stored tokens:

```bash
rm token.json
```

No calendar data is ever stored on disk.
