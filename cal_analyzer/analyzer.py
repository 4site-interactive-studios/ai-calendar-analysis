"""Analytics engine for calendar data."""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime
from typing import Optional

from .classifier import MeetingType, classify_meeting, get_external_orgs


def _quarter(dt: datetime) -> str:
    """Return quarter string like '2025-Q1'."""
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{q}"


def _month(dt: datetime) -> str:
    """Return month string like '2025-01'."""
    return dt.strftime("%Y-%m")


def _year(dt: datetime) -> str:
    return str(dt.year)


def _week(dt: datetime) -> str:
    """Return ISO week string like '2025-W03'."""
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _day(dt: datetime) -> str:
    """Return date string like '2025-02-03'."""
    return dt.strftime("%Y-%m-%d")


def analyze_events(events: list[dict], config: dict,
                    exclude_types: Optional[set] = None) -> dict:
    """Run full analytics on parsed events.

    Args:
        events: List of parsed event dicts.
        config: Application config dict.
        exclude_types: Set of MeetingType values to exclude from tallies.
            Defaults to {"hold", "ooo", "all_day"}.

    Returns a comprehensive analytics dictionary with breakdowns
    by time period, meeting type, participants, and more.
    """
    if exclude_types is None:
        exclude_types = {"hold", "ooo", "all_day", "solo"}

    results = {
        "total_events": 0,
        "total_hours": 0.0,
        "excluded": defaultdict(lambda: {"count": 0, "hours": 0.0}),
        "by_month": defaultdict(lambda: _empty_bucket()),
        "by_quarter": defaultdict(lambda: _empty_bucket()),
        "by_year": defaultdict(lambda: _empty_bucket()),
        "by_week": defaultdict(lambda: _empty_bucket()),
        "by_day": defaultdict(lambda: _empty_bucket()),
        "by_type": defaultdict(lambda: _empty_bucket()),
        "by_day_of_week": defaultdict(lambda: _empty_bucket()),
        "by_hour_of_day": defaultdict(lambda: _empty_bucket()),
        "participants": defaultdict(lambda: {
            "count": 0, "total_minutes": 0.0, "meetings": []
        }),
        "organization_breakdown": defaultdict(lambda: _empty_bucket()),
        "recurring_vs_oneoff": {"recurring": _empty_bucket(), "one-off": _empty_bucket()},
        "duration_distribution": defaultdict(int),
        "busiest_days": [],
        "daily_hours": {},  # mean/median hours per day
        "events": [],  # enriched events
    }

    daily_totals = defaultdict(lambda: {"count": 0, "minutes": 0.0})
    # Per-day hours by type (excludes holds)
    daily_hours_all = defaultdict(float)
    daily_hours_internal = defaultdict(float)
    daily_hours_external = defaultdict(float)

    for event in events:
        meeting_type = classify_meeting(event, config)
        ext_orgs = get_external_orgs(event, config) if meeting_type == MeetingType.EXTERNAL else []
        duration = event["duration_minutes"]
        start = event["start"]

        # Enrich event
        enriched = {**event, "meeting_type": meeting_type.value, "organizations": ext_orgs}
        results["events"].append(enriched)

        # Track excluded types separately -- not counted in main tallies
        if meeting_type.value in exclude_types:
            results["excluded"][meeting_type.value]["count"] += 1
            results["excluded"][meeting_type.value]["hours"] += duration / 60
            continue

        results["total_events"] += 1
        results["total_hours"] += duration / 60

        # Time period buckets
        for period_key, period_fn in [
            ("by_month", _month),
            ("by_quarter", _quarter),
            ("by_year", _year),
            ("by_week", _week),
            ("by_day", _day),
        ]:
            key = period_fn(start)
            _add_to_bucket(results[period_key][key], duration, meeting_type)

        # Meeting type bucket
        _add_to_bucket(results["by_type"][meeting_type.value], duration, meeting_type)

        # Day of week (Monday=0)
        day_name = start.strftime("%A")
        _add_to_bucket(results["by_day_of_week"][day_name], duration, meeting_type)

        # Hour of day
        hour_label = start.strftime("%I %p").lstrip("0")
        _add_to_bucket(results["by_hour_of_day"][hour_label], duration, meeting_type)

        # Participants
        for att in event.get("attendees", []):
            email = att.get("email", "")
            if att.get("self") or not email or email.endswith("calendar.google.com"):
                continue
            raw_name = att.get("name", "")
            # Treat names containing '@' as unparsed emails, not real names
            real_name = raw_name if raw_name and "@" not in raw_name else ""
            name = real_name or _name_from_email(email)
            p = results["participants"][email]
            p["count"] += 1
            p["total_minutes"] += duration
            # Prefer a real display name over a derived one
            if not p.get("name") or "@" in p.get("name", ""):
                p["name"] = name
            elif real_name:
                p["name"] = real_name
            p["email"] = email

        # Organization breakdown (external meetings)
        for org in ext_orgs:
            _add_to_bucket(results["organization_breakdown"][org], duration, meeting_type)

        # Recurring vs one-off
        r_key = "recurring" if event.get("recurring") else "one-off"
        _add_to_bucket(results["recurring_vs_oneoff"][r_key], duration, meeting_type)

        # Duration distribution
        if duration <= 15:
            results["duration_distribution"]["0-15 min"] += 1
        elif duration <= 30:
            results["duration_distribution"]["16-30 min"] += 1
        elif duration <= 60:
            results["duration_distribution"]["31-60 min"] += 1
        elif duration <= 90:
            results["duration_distribution"]["61-90 min"] += 1
        else:
            results["duration_distribution"]["90+ min"] += 1

        # Daily totals for busiest days and per-day metrics
        day_key = start.strftime("%Y-%m-%d")
        daily_totals[day_key]["count"] += 1
        daily_totals[day_key]["minutes"] += duration
        hours = duration / 60
        daily_hours_all[day_key] += hours
        if meeting_type == MeetingType.INTERNAL:
            daily_hours_internal[day_key] += hours
        elif meeting_type == MeetingType.EXTERNAL:
            daily_hours_external[day_key] += hours

    # Compute busiest days (top 10)
    sorted_days = sorted(daily_totals.items(), key=lambda x: x[1]["minutes"], reverse=True)
    results["busiest_days"] = [
        {"date": d, "meetings": v["count"], "hours": round(v["minutes"] / 60, 1)}
        for d, v in sorted_days[:10]
    ]

    # Compute daily hours statistics (only days that had meetings)
    results["daily_hours"] = _compute_daily_stats(
        daily_hours_all, daily_hours_internal, daily_hours_external,
    )

    # Convert defaultdicts to regular dicts for serialization
    results["by_month"] = dict(sorted(results["by_month"].items()))
    results["by_quarter"] = dict(sorted(results["by_quarter"].items()))
    results["by_year"] = dict(sorted(results["by_year"].items()))
    results["by_week"] = dict(sorted(results["by_week"].items()))
    results["by_day"] = dict(sorted(results["by_day"].items()))
    results["by_type"] = dict(results["by_type"])
    results["by_day_of_week"] = dict(results["by_day_of_week"])
    results["by_hour_of_day"] = dict(results["by_hour_of_day"])
    results["participants"] = dict(results["participants"])
    results["organization_breakdown"] = dict(results["organization_breakdown"])
    results["excluded"] = {k: dict(v) for k, v in results["excluded"].items()}
    results["duration_distribution"] = dict(results["duration_distribution"])

    return results


def _name_from_email(email: str) -> str:
    """Derive a display name from an email address.

    'tayo@4sitestudios.com' -> 'Tayo'
    'bryan.casler@gmail.com' -> 'Bryan Casler'
    'mary-jane@example.com' -> 'Mary Jane'
    """
    local = email.split("@")[0] if "@" in email else email
    # Split on dots, hyphens, underscores
    parts = local.replace("-", ".").replace("_", ".").split(".")
    return " ".join(p.title() for p in parts if p)


def _compute_daily_stats(
    daily_all: dict, daily_internal: dict, daily_external: dict,
) -> dict:
    """Compute mean/median hours per day for all, internal, and external.

    Returns stats for both workdays-only (M-F) and all days.
    """
    def _stats(values: list[float]) -> dict:
        if not values:
            return {"mean": 0.0, "median": 0.0, "days": 0}
        return {
            "mean": round(statistics.mean(values), 2),
            "median": round(statistics.median(values), 2),
            "days": len(values),
        }

    def _split(d: dict):
        work = {}
        every = {}
        for day_key, val in d.items():
            every[day_key] = val
            dt = datetime.strptime(day_key, "%Y-%m-%d")
            if dt.weekday() < 5:  # Mon-Fri
                work[day_key] = val
        return work, every

    work_all, every_all = _split(daily_all)
    work_int, every_int = _split(daily_internal)
    work_ext, every_ext = _split(daily_external)

    return {
        "workdays": {
            "all": _stats(list(work_all.values())),
            "internal": _stats(list(work_int.values())),
            "external": _stats(list(work_ext.values())),
        },
        "all_days": {
            "all": _stats(list(every_all.values())),
            "internal": _stats(list(every_int.values())),
            "external": _stats(list(every_ext.values())),
        },
    }


def _empty_bucket() -> dict:
    return {
        "count": 0,
        "total_minutes": 0.0,
        "total_hours": 0.0,
        "type_breakdown": defaultdict(int),
    }


def _add_to_bucket(bucket: dict, duration_minutes: float, meeting_type: MeetingType):
    bucket["count"] += 1
    bucket["total_minutes"] += duration_minutes
    bucket["total_hours"] = round(bucket["total_minutes"] / 60, 2)
    bucket["type_breakdown"][meeting_type.value] += 1


def filter_events_by_date(events: list[dict],
                           start_date: Optional[datetime] = None,
                           end_date: Optional[datetime] = None) -> list[dict]:
    """Filter events to those within the given date range."""
    filtered = []
    for event in events:
        dt = event["start"]
        if start_date and dt < start_date:
            continue
        if end_date and dt > end_date:
            continue
        filtered.append(event)
    return filtered


def compute_yoy(current_stats: dict, previous_stats: dict) -> dict:
    """Compute Year-over-Year comparison between two period summary stats.

    Returns a dict keyed by metric name, each containing current value,
    previous value, and percentage change.
    """
    def pct_change(current, previous):
        if previous == 0:
            return None if current == 0 else 100.0
        return round(((current - previous) / previous) * 100, 1)

    metrics = [
        "total_events", "total_hours", "avg_duration_minutes",
        "meetings_per_working_day", "internal_count", "external_count",
        "internal_hours", "external_hours",
    ]

    result = {}
    for m in metrics:
        cur = current_stats.get(m, 0)
        prev = previous_stats.get(m, 0)
        result[m] = {
            "current": cur,
            "previous": prev,
            "change_pct": pct_change(cur, prev),
        }
    return result


def get_top_participants(results: dict, n: int = 20) -> list[dict]:
    """Return top N participants by meeting count."""
    participants = list(results["participants"].values())
    participants.sort(key=lambda p: p["count"], reverse=True)
    return participants[:n]


def get_summary_stats(results: dict) -> dict:
    """Compute high-level summary statistics."""
    total = results["total_events"]
    excluded = dict(results.get("excluded", {}))

    if total == 0:
        return {
            "total_events": 0, "total_hours": 0,
            "excluded": excluded,
            "daily_hours": results.get("daily_hours", {}),
        }

    type_counts = results["by_type"]
    avg_duration = (results["total_hours"] * 60) / total if total else 0
    avg_attendees = (
        sum(e["attendee_count"] for e in results["events"]
            if e.get("meeting_type") in dict(type_counts))
        / total if total else 0
    )

    # Meetings per working day (approximate)
    if results["by_month"]:
        months = len(results["by_month"])
        working_days = months * 21  # ~21 working days per month
        meetings_per_day = total / working_days
    else:
        meetings_per_day = 0

    return {
        "total_events": total,
        "total_hours": round(results["total_hours"], 1),
        "avg_duration_minutes": round(avg_duration, 1),
        "avg_attendees": round(avg_attendees, 1),
        "meetings_per_working_day": round(meetings_per_day, 1),
        "internal_count": type_counts.get("internal", {}).get("count", 0),
        "external_count": type_counts.get("external", {}).get("count", 0),
        "solo_count": type_counts.get("solo", {}).get("count", 0),
        "recurring_count": results["recurring_vs_oneoff"]["recurring"]["count"],
        "oneoff_count": results["recurring_vs_oneoff"]["one-off"]["count"],
        "internal_hours": type_counts.get("internal", {}).get("total_hours", 0),
        "external_hours": type_counts.get("external", {}).get("total_hours", 0),
        "excluded": excluded,
        "daily_hours": results.get("daily_hours", {}),
    }
