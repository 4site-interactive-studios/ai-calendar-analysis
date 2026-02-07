"""Flask web application for calendar analytics dashboard.

All calendar data is processed in-memory only. Nothing is persisted
to disk or stored in sessions beyond the current page load.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta
from flask import Flask, render_template, request, jsonify

from cal_analyzer.analyzer import (
    analyze_events,
    get_summary_stats,
    get_top_participants,
    filter_events_by_date,
    compute_yoy,
)
from cal_analyzer.config import load_config


def create_app(config_path: str = "config.yaml"):
    app = Flask(__name__, template_folder="templates")
    app.config["SECRET_KEY"] = "local-only-not-for-production"

    cfg = load_config(config_path)

    # In-memory event cache (local tool, single user)
    _cache = {"events": [], "source": ""}

    @app.route("/")
    def index():
        return render_template("dashboard.html", config=cfg)

    def _build_response(events, source_label, start_date=None, end_date=None, exclude_types=None):
        """Run analytics and build JSON response."""
        results = analyze_events(events, cfg, exclude_types=exclude_types)
        stats = get_summary_stats(results)
        top_people = get_top_participants(results, 25)

        return {
            "source": source_label,
            "event_count": len(events),
            "date_range": {
                "start": start_date.strftime("%Y-%m-%d") if start_date else "all",
                "end": end_date.strftime("%Y-%m-%d") if end_date else "present",
            },
            "summary": stats,
            "by_month": _serialize_buckets(results["by_month"]),
            "by_quarter": _serialize_buckets(results["by_quarter"]),
            "by_year": _serialize_buckets(results["by_year"]),
            "by_week": _serialize_buckets(results["by_week"]),
            "by_day": _serialize_buckets(results["by_day"]),
            "by_type": _serialize_buckets(results["by_type"]),
            "by_day_of_week": _serialize_buckets(results["by_day_of_week"]),
            "duration_distribution": results["duration_distribution"],
            "organization_breakdown": _serialize_buckets(results["organization_breakdown"]),
            "recurring_vs_oneoff": _serialize_buckets(results["recurring_vs_oneoff"]),
            "busiest_days": results["busiest_days"],
            "top_participants": [
                {
                    "name": p.get("name", ""),
                    "email": p.get("email", ""),
                    "count": p["count"],
                    "hours": round(p["total_minutes"] / 60, 1),
                }
                for p in top_people
            ],
        }

    @app.route("/api/analyze", methods=["POST"])
    def api_analyze():
        """Load ALL events from source (no date filtering) and cache them.

        Returns analysis of the full dataset.
        """
        ical_url = request.form.get("ical_url", "").strip()
        ical_file = request.files.get("ical_file")

        events = None
        source_label = ""

        if ical_file and ical_file.filename:
            from icalendar import Calendar
            from cal_analyzer.ical_import import ical_to_parsed_events
            cal = Calendar.from_ical(ical_file.read())
            events = ical_to_parsed_events(cal, None, None)
            source_label = f"File: {ical_file.filename}"

        elif ical_url:
            from cal_analyzer.ical_import import get_events_from_ical_url
            try:
                events = get_events_from_ical_url(ical_url, None, None)
                source_label = "iCal URL"
            except Exception as e:
                return jsonify({"error": f"Failed to fetch iCal URL: {e}"}), 400

        else:
            try:
                from cal_analyzer.auth import get_calendar_service
                from cal_analyzer.fetcher import get_parsed_events
                service = get_calendar_service(
                    credentials_file=cfg.get("credentials_file", "credentials.json"),
                    token_file=cfg.get("token_file", "token.json"),
                )
                events = get_parsed_events(service, cfg.get("calendar_id", "primary"),
                                           None, None)
                source_label = "Google Calendar API"
            except Exception as e:
                return jsonify({
                    "error": (
                        "No data source provided and Google Calendar API not configured. "
                        "Upload an .ics file or paste an iCal URL."
                    ),
                    "detail": str(e),
                }), 400

        if events is None or len(events) == 0:
            return jsonify({"error": "No events loaded"}), 400

        # Cache events for subsequent filter requests
        _cache["events"] = events
        _cache["source"] = source_label

        # Find date range of all events
        dates = [e["start"] for e in events]
        min_date = min(dates)
        max_date = max(dates)

        response = _build_response(events, source_label)
        response["total_event_count"] = len(events)
        response["data_range"] = {
            "min_date": min_date.strftime("%Y-%m-%d"),
            "max_date": max_date.strftime("%Y-%m-%d"),
        }
        response["yoy"] = None

        # Also return default exclude types so the UI knows the initial state
        response["exclude_types"] = ["hold", "ooo", "all_day", "solo"]
        return jsonify(response)

    @app.route("/api/filter", methods=["POST"])
    def api_filter():
        """Re-analyze cached events with a date filter.

        Also computes YoY comparison (same period shifted 1 year back)
        when a date range is specified.
        """
        if not _cache["events"]:
            return jsonify({"error": "No data loaded. Please load a calendar first."}), 400

        data = request.get_json() or {}
        start_str = data.get("start_date", "")
        end_str = data.get("end_date", "")
        exclude_list = data.get("exclude_types", None)
        exclude_types = set(exclude_list) if exclude_list is not None else None

        start_date = _parse_date(start_str) if start_str else None
        end_date = _parse_date(end_str) if end_str else None

        # Filter events
        filtered = filter_events_by_date(_cache["events"], start_date, end_date)
        if not filtered:
            return jsonify({"error": "No events in selected date range"}), 400

        response = _build_response(filtered, _cache["source"], start_date, end_date, exclude_types)
        response["total_event_count"] = len(_cache["events"])

        # Data range of all cached events
        all_dates = [e["start"] for e in _cache["events"]]
        response["data_range"] = {
            "min_date": min(all_dates).strftime("%Y-%m-%d"),
            "max_date": max(all_dates).strftime("%Y-%m-%d"),
        }

        # Compute YoY comparison
        yoy = None
        if start_date and end_date:
            prev_start = start_date - relativedelta(years=1)
            prev_end = end_date - relativedelta(years=1)
            prev_filtered = filter_events_by_date(_cache["events"], prev_start, prev_end)
            if prev_filtered:
                current_stats = get_summary_stats(analyze_events(filtered, cfg, exclude_types=exclude_types))
                prev_stats = get_summary_stats(analyze_events(prev_filtered, cfg, exclude_types=exclude_types))
                yoy = compute_yoy(current_stats, prev_stats)
                yoy["previous_period"] = {
                    "start": prev_start.strftime("%Y-%m-%d"),
                    "end": prev_end.strftime("%Y-%m-%d"),
                    "event_count": len(prev_filtered),
                }
        response["yoy"] = yoy

        return jsonify(response)

    return app


def _serialize_buckets(data: dict) -> dict:
    """Convert bucket data to JSON-safe format."""
    out = {}
    for key, bucket in data.items():
        out[key] = {
            "count": bucket["count"],
            "total_hours": bucket["total_hours"],
            "type_breakdown": dict(bucket.get("type_breakdown", {})),
        }
    return out


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
