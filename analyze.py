#!/usr/bin/env python3
"""4Site Google Calendar Analytics CLI.

Analyze your Google Calendar to understand meeting patterns,
time allocation, and participant breakdowns.

Data sources:
  - Google Calendar API (requires OAuth credentials)
  - iCal (.ics) file import
  - iCal URL import

Privacy: All data is processed in-memory only. No calendar data
is stored on disk. Only OAuth tokens are persisted (and can be
deleted at any time).
"""

import sys
from datetime import datetime, timezone

import click
from dateutil.relativedelta import relativedelta
from rich.console import Console

from cal_analyzer.analyzer import analyze_events
from cal_analyzer.config import load_config
from cal_analyzer.reporter import (
    console,
    export_csv,
    export_json,
    print_full_report,
    print_summary,
    print_time_breakdown,
    print_meeting_types,
    print_day_of_week,
    print_duration_distribution,
    print_top_participants,
    print_organization_breakdown,
    print_busiest_days,
)

PERIOD_CHOICES = ["month", "quarter", "year", "week"]


@click.group(invoke_without_command=True)
@click.option("--config", "-c", default="config.yaml", help="Path to config YAML file.")
@click.option("--ical-file", type=click.Path(exists=True), help="Path to .ics file to import.")
@click.option("--ical-url", type=str, help="URL to an iCal feed.")
@click.option("--start", type=str, help="Start date (YYYY-MM-DD). Default: 1 year ago.")
@click.option("--end", type=str, help="End date (YYYY-MM-DD). Default: today.")
@click.option("--period", type=click.Choice(PERIOD_CHOICES), default="month",
              help="Time period for breakdown.")
@click.option("--export-json", "json_path", type=str, help="Export results to JSON file.")
@click.option("--export-csv", "csv_path", type=str, help="Export monthly breakdown to CSV.")
@click.option("--top-n", type=int, default=20, help="Number of top participants to show.")
@click.pass_context
def cli(ctx, config, ical_file, ical_url, start, end, period, json_path, csv_path, top_n):
    """4Site Calendar Analytics -- Understand your meeting time.

    By default, connects to Google Calendar via API.
    Use --ical-file or --ical-url to analyze an iCal source instead.

    \b
    Examples:
      python analyze.py                         # Full report, last 12 months
      python analyze.py --period quarter         # Quarterly breakdown
      python analyze.py --start 2025-01-01       # From Jan 2025 to now
      python analyze.py --ical-file cal.ics      # Analyze a .ics file
      python analyze.py --ical-url https://...   # Analyze an iCal URL
      python analyze.py --export-csv report.csv  # Export to CSV
      python analyze.py summary                  # Summary only
    """
    cfg = load_config(config)
    ctx.ensure_object(dict)
    ctx.obj["config"] = cfg

    # Parse dates
    now = datetime.now(timezone.utc)
    start_date = _parse_date(start) if start else now - relativedelta(years=1)
    end_date = _parse_date(end) if end else now

    ctx.obj["start_date"] = start_date
    ctx.obj["end_date"] = end_date

    # Fetch events from the chosen source
    events = _load_events(cfg, ical_file, ical_url, start_date, end_date)
    if events is None:
        return

    console.print(
        f"[dim]Loaded {len(events)} events "
        f"({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})[/dim]"
    )

    # Run analytics
    results = analyze_events(events, cfg)
    ctx.obj["results"] = results

    # If no subcommand, print full report
    if ctx.invoked_subcommand is None:
        print_full_report(results)

        if json_path:
            export_json(results, json_path)
        if csv_path:
            export_csv(results, csv_path)


@cli.command()
@click.pass_context
def summary(ctx):
    """Show only the summary panel."""
    print_summary(ctx.obj["results"])


@cli.command()
@click.option("--period", type=click.Choice(PERIOD_CHOICES), default="month")
@click.pass_context
def breakdown(ctx, period):
    """Show time period breakdown."""
    print_time_breakdown(ctx.obj["results"], period)


@cli.command()
@click.pass_context
def types(ctx):
    """Show meeting type breakdown."""
    print_meeting_types(ctx.obj["results"])


@cli.command()
@click.option("-n", type=int, default=20, help="Number of participants to show.")
@click.pass_context
def participants(ctx, n):
    """Show top meeting participants."""
    print_top_participants(ctx.obj["results"], n)


@cli.command()
@click.pass_context
def orgs(ctx):
    """Show external organization meeting breakdown."""
    print_organization_breakdown(ctx.obj["results"])


@cli.command()
@click.pass_context
def schedule(ctx):
    """Show day-of-week and duration patterns."""
    print_day_of_week(ctx.obj["results"])
    print_duration_distribution(ctx.obj["results"])
    print_busiest_days(ctx.obj["results"])


def _load_events(cfg, ical_file, ical_url, start_date, end_date):
    """Load events from the appropriate source."""
    if ical_file:
        console.print(f"[bold]Loading from iCal file:[/bold] {ical_file}")
        from cal_analyzer.ical_import import get_events_from_ical_file
        return get_events_from_ical_file(ical_file, start_date, end_date)

    if ical_url:
        console.print(f"[bold]Loading from iCal URL...[/bold]")
        from cal_analyzer.ical_import import get_events_from_ical_url
        return get_events_from_ical_url(ical_url, start_date, end_date)

    # Default: Google Calendar API
    console.print("[bold]Connecting to Google Calendar API...[/bold]")
    try:
        from cal_analyzer.auth import get_calendar_service
        from cal_analyzer.fetcher import get_parsed_events
        service = get_calendar_service(
            credentials_file=cfg.get("credentials_file", "credentials.json"),
            token_file=cfg.get("token_file", "token.json"),
        )
        return get_parsed_events(service, cfg.get("calendar_id", "primary"),
                                 start_date, end_date)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        console.print(
            "\n[yellow]Tip:[/yellow] You can also analyze calendars without API setup:\n"
            "  python analyze.py --ical-file your_calendar.ics\n"
            "  python analyze.py --ical-url https://calendar.google.com/...ical\n"
        )
        return None
    except Exception as e:
        console.print(f"[red]Error connecting to Google Calendar: {e}[/red]")
        return None


def _parse_date(date_str: str) -> datetime:
    """Parse a YYYY-MM-DD string to a timezone-aware datetime."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        console.print(f"[red]Invalid date format: {date_str}. Use YYYY-MM-DD.[/red]")
        sys.exit(1)


if __name__ == "__main__":
    cli()
