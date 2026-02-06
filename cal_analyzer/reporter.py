"""Rich terminal output for calendar analytics."""

import csv
import io
import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .analyzer import get_summary_stats, get_top_participants

console = Console()


def _hours_str(minutes: float) -> str:
    h = minutes / 60
    if h >= 1:
        return f"{h:.1f}h"
    return f"{minutes:.0f}m"


def _pct(part: int, total: int) -> str:
    if total == 0:
        return "0%"
    return f"{part / total * 100:.1f}%"


def print_summary(results: dict):
    """Print a high-level summary panel."""
    stats = get_summary_stats(results)

    summary_lines = [
        f"[bold]Total Meetings:[/bold]        {stats['total_events']}",
        f"[bold]Total Meeting Hours:[/bold]    {stats['total_hours']}h",
        f"[bold]Avg Duration:[/bold]           {stats['avg_duration_minutes']} min",
        f"[bold]Avg Attendees:[/bold]          {stats['avg_attendees']}",
        f"[bold]Meetings / Work Day:[/bold]    {stats['meetings_per_working_day']}",
        "",
        f"[green]Internal:[/green]  {stats['internal_count']} meetings ({stats['internal_hours']}h)",
        f"[yellow]External:[/yellow]  {stats['external_count']} meetings ({stats['external_hours']}h)",
        f"[dim]Solo:[/dim]      {stats['solo_count']} meetings",
        "",
        f"[bold]Recurring:[/bold]  {stats['recurring_count']}  |  [bold]One-off:[/bold]  {stats['oneoff_count']}",
    ]

    console.print(Panel(
        "\n".join(summary_lines),
        title="Calendar Analytics Summary",
        border_style="bright_blue",
    ))


def print_time_breakdown(results: dict, period: str = "month"):
    """Print meetings broken down by time period."""
    key_map = {
        "month": "by_month",
        "quarter": "by_quarter",
        "year": "by_year",
        "week": "by_week",
    }
    data_key = key_map.get(period, "by_month")
    data = results.get(data_key, {})

    if not data:
        console.print(f"[dim]No data for period: {period}[/dim]")
        return

    table = Table(title=f"Meetings by {period.title()}", show_lines=False)
    table.add_column("Period", style="bold")
    table.add_column("Meetings", justify="right")
    table.add_column("Hours", justify="right")
    table.add_column("Internal", justify="right", style="green")
    table.add_column("External", justify="right", style="yellow")
    table.add_column("Solo", justify="right", style="dim")

    for period_name, bucket in data.items():
        tb = bucket.get("type_breakdown", {})
        table.add_row(
            period_name,
            str(bucket["count"]),
            f"{bucket['total_hours']:.1f}",
            str(tb.get("internal", 0)),
            str(tb.get("external", 0)),
            str(tb.get("solo", 0)),
        )

    console.print(table)
    console.print()


def print_meeting_types(results: dict):
    """Print meeting type breakdown."""
    data = results.get("by_type", {})
    total = results["total_events"]

    table = Table(title="Meeting Type Breakdown")
    table.add_column("Type", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("% of Total", justify="right")
    table.add_column("Hours", justify="right")

    type_styles = {
        "internal": "green",
        "external": "yellow",
        "solo": "dim",
    }

    for mtype, bucket in sorted(data.items()):
        style = type_styles.get(mtype, "")
        table.add_row(
            Text(mtype.title(), style=style),
            str(bucket["count"]),
            _pct(bucket["count"], total),
            f"{bucket['total_hours']:.1f}",
        )

    console.print(table)
    console.print()


def print_day_of_week(results: dict):
    """Print meetings by day of week."""
    data = results.get("by_day_of_week", {})
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    table = Table(title="Meetings by Day of Week")
    table.add_column("Day", style="bold")
    table.add_column("Meetings", justify="right")
    table.add_column("Hours", justify="right")
    table.add_column("Bar", min_width=30)

    max_count = max((b["count"] for b in data.values()), default=1)

    for day in day_order:
        if day not in data:
            continue
        bucket = data[day]
        bar_len = int((bucket["count"] / max_count) * 25) if max_count > 0 else 0
        bar = "█" * bar_len
        table.add_row(day, str(bucket["count"]), f"{bucket['total_hours']:.1f}", f"[cyan]{bar}[/cyan]")

    console.print(table)
    console.print()


def print_duration_distribution(results: dict):
    """Print meeting duration distribution."""
    data = results.get("duration_distribution", {})
    total = sum(data.values())
    order = ["0-15 min", "16-30 min", "31-60 min", "61-90 min", "90+ min"]

    table = Table(title="Meeting Duration Distribution")
    table.add_column("Duration", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("% of Total", justify="right")
    table.add_column("Bar", min_width=30)

    max_count = max(data.values(), default=1)

    for bucket_name in order:
        count = data.get(bucket_name, 0)
        bar_len = int((count / max_count) * 25) if max_count > 0 else 0
        bar = "█" * bar_len
        table.add_row(bucket_name, str(count), _pct(count, total), f"[magenta]{bar}[/magenta]")

    console.print(table)
    console.print()


def print_top_participants(results: dict, n: int = 20):
    """Print the top meeting participants."""
    participants = get_top_participants(results, n)

    if not participants:
        console.print("[dim]No participant data available.[/dim]")
        return

    table = Table(title=f"Top {n} Meeting Participants")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Email", style="dim")
    table.add_column("Meetings", justify="right")
    table.add_column("Total Time", justify="right")

    for i, p in enumerate(participants, 1):
        table.add_row(
            str(i),
            p.get("name", ""),
            p.get("email", ""),
            str(p["count"]),
            _hours_str(p["total_minutes"]),
        )

    console.print(table)
    console.print()


def print_organization_breakdown(results: dict):
    """Print time spent with each external organization."""
    data = results.get("organization_breakdown", {})

    if not data:
        console.print("[dim]No external organization meetings found.[/dim]")
        return

    table = Table(title="External Organization Breakdown")
    table.add_column("Organization", style="bold yellow")
    table.add_column("Meetings", justify="right")
    table.add_column("Hours", justify="right")

    for org, bucket in sorted(data.items(), key=lambda x: x[1]["total_hours"], reverse=True):
        table.add_row(org, str(bucket["count"]), f"{bucket['total_hours']:.1f}")

    console.print(table)
    console.print()


def print_busiest_days(results: dict, n: int = 10):
    """Print the busiest days."""
    days = results.get("busiest_days", [])[:n]

    if not days:
        return

    table = Table(title=f"Top {n} Busiest Days")
    table.add_column("Date", style="bold")
    table.add_column("Meetings", justify="right")
    table.add_column("Hours", justify="right")

    for d in days:
        table.add_row(d["date"], str(d["meetings"]), str(d["hours"]))

    console.print(table)
    console.print()


def print_full_report(results: dict):
    """Print the complete analytics report."""
    console.print()
    print_summary(results)
    console.print()
    print_time_breakdown(results, "year")
    print_time_breakdown(results, "quarter")
    print_time_breakdown(results, "month")
    print_meeting_types(results)
    print_day_of_week(results)
    print_duration_distribution(results)
    print_top_participants(results)
    print_organization_breakdown(results)
    print_busiest_days(results)


def export_json(results: dict, output_path: str):
    """Export analytics to JSON (excludes raw event PII)."""
    safe_results = _strip_pii(results)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(safe_results, f, indent=2, default=str)
    console.print(f"[green]JSON report saved to:[/green] {path}")


def export_csv(results: dict, output_path: str):
    """Export monthly breakdown to CSV."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Period", "Meetings", "Hours", "Internal", "External", "Solo"
        ])
        for period_name, bucket in results.get("by_month", {}).items():
            tb = bucket.get("type_breakdown", {})
            writer.writerow([
                period_name,
                bucket["count"],
                f"{bucket['total_hours']:.1f}",
                tb.get("internal", 0),
                tb.get("external", 0),
                tb.get("solo", 0),
            ])

    console.print(f"[green]CSV report saved to:[/green] {path}")


def _strip_pii(results: dict) -> dict:
    """Remove PII from results before export.

    Strips individual event details and participant emails,
    keeping only aggregate statistics.
    """
    safe = {k: v for k, v in results.items() if k != "events"}

    # Replace participant details with anonymized stats
    if "participants" in safe:
        safe["participant_count"] = len(safe["participants"])
        del safe["participants"]

    return safe
