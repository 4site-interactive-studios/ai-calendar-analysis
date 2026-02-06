"""Analytics engine for calendar data."""

from __future__ import annotations

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


def analyze_events(events: list[dict], config: dict) -> dict:
    """Run full analytics on parsed events.

    Returns a comprehensive analytics dictionary with breakdowns
    by time period, meeting type, participants, and more.
    """
    results = {
        "total_events": 0,
        "total_hours": 0.0,
        "by_month": defaultdict(lambda: _empty_bucket()),
        "by_quarter": defaultdict(lambda: _empty_bucket()),
        "by_year": defaultdict(lambda: _empty_bucket()),
        "by_week": defaultdict(lambda: _empty_bucket()),
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
        "events": [],  # enriched events
    }

    daily_totals = defaultdict(lambda: {"count": 0, "minutes": 0.0})

    for event in events:
        meeting_type = classify_meeting(event, config)
        ext_orgs = get_external_orgs(event, config) if meeting_type == MeetingType.EXTERNAL else []
        duration = event["duration_minutes"]
        start = event["start"]

        # Enrich event
        enriched = {**event, "meeting_type": meeting_type.value, "organizations": ext_orgs}
        results["events"].append(enriched)

        results["total_events"] += 1
        results["total_hours"] += duration / 60

        # Time period buckets
        for period_key, period_fn in [
            ("by_month", _month),
            ("by_quarter", _quarter),
            ("by_year", _year),
            ("by_week", _week),
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
            name = att.get("name") or email
            p = results["participants"][email]
            p["count"] += 1
            p["total_minutes"] += duration
            p["name"] = name
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

        # Daily totals for busiest days
        day_key = start.strftime("%Y-%m-%d")
        daily_totals[day_key]["count"] += 1
        daily_totals[day_key]["minutes"] += duration

    # Compute busiest days (top 10)
    sorted_days = sorted(daily_totals.items(), key=lambda x: x[1]["minutes"], reverse=True)
    results["busiest_days"] = [
        {"date": d, "meetings": v["count"], "hours": round(v["minutes"] / 60, 1)}
        for d, v in sorted_days[:10]
    ]

    # Convert defaultdicts to regular dicts for serialization
    results["by_month"] = dict(sorted(results["by_month"].items()))
    results["by_quarter"] = dict(sorted(results["by_quarter"].items()))
    results["by_year"] = dict(sorted(results["by_year"].items()))
    results["by_week"] = dict(sorted(results["by_week"].items()))
    results["by_type"] = dict(results["by_type"])
    results["by_day_of_week"] = dict(results["by_day_of_week"])
    results["by_hour_of_day"] = dict(results["by_hour_of_day"])
    results["participants"] = dict(results["participants"])
    results["organization_breakdown"] = dict(results["organization_breakdown"])
    results["duration_distribution"] = dict(results["duration_distribution"])

    return results


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


def get_top_participants(results: dict, n: int = 20) -> list[dict]:
    """Return top N participants by meeting count."""
    participants = list(results["participants"].values())
    participants.sort(key=lambda p: p["count"], reverse=True)
    return participants[:n]


def get_summary_stats(results: dict) -> dict:
    """Compute high-level summary statistics."""
    total = results["total_events"]
    if total == 0:
        return {"total_events": 0, "total_hours": 0}

    type_counts = results["by_type"]
    avg_duration = (results["total_hours"] * 60) / total if total else 0
    avg_attendees = (
        sum(e["attendee_count"] for e in results["events"]) / total
        if total else 0
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
    }
