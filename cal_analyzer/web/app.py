"""Flask web application for calendar analytics dashboard.

All calendar data is processed in-memory only. Nothing is persisted
to disk or stored in sessions beyond the current page load.
"""

import json
from collections import defaultdict
from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta
from flask import Flask, render_template, request, jsonify

from cal_analyzer.analyzer import analyze_events, get_summary_stats, get_top_participants
from cal_analyzer.config import load_config


def create_app(config_path: str = "config.yaml"):
    app = Flask(__name__, template_folder="templates")
    app.config["SECRET_KEY"] = "local-only-not-for-production"

    cfg = load_config(config_path)

    @app.route("/")
    def index():
        return render_template("dashboard.html", config=cfg)

    @app.route("/api/analyze", methods=["POST"])
    def api_analyze():
        """Analyze calendar data from an uploaded .ics file or iCal URL.

        Accepts multipart form with either:
          - ical_file: uploaded .ics file
          - ical_url: URL to iCal feed

        Also accepts optional:
          - start_date: YYYY-MM-DD
          - end_date: YYYY-MM-DD

        Returns JSON analytics results. No data is stored.
        """
        now = datetime.now(timezone.utc)
        start_str = request.form.get("start_date", "")
        end_str = request.form.get("end_date", "")

        start_date = _parse_date(start_str) if start_str else None
        end_date = _parse_date(end_str) if end_str else None

        # Determine source
        ical_url = request.form.get("ical_url", "").strip()
        ical_file = request.files.get("ical_file")

        events = None
        source_label = ""

        if ical_file and ical_file.filename:
            from icalendar import Calendar
            from cal_analyzer.ical_import import ical_to_parsed_events
            cal = Calendar.from_ical(ical_file.read())
            events = ical_to_parsed_events(cal, start_date, end_date)
            source_label = f"File: {ical_file.filename}"

        elif ical_url:
            from cal_analyzer.ical_import import get_events_from_ical_url
            try:
                events = get_events_from_ical_url(ical_url, start_date, end_date)
                source_label = "iCal URL"
            except Exception as e:
                return jsonify({"error": f"Failed to fetch iCal URL: {e}"}), 400

        else:
            # Try Google Calendar API
            try:
                from cal_analyzer.auth import get_calendar_service
                from cal_analyzer.fetcher import get_parsed_events
                service = get_calendar_service(
                    credentials_file=cfg.get("credentials_file", "credentials.json"),
                    token_file=cfg.get("token_file", "token.json"),
                )
                events = get_parsed_events(service, cfg.get("calendar_id", "primary"),
                                           start_date, end_date)
                source_label = "Google Calendar API"
            except Exception as e:
                return jsonify({
                    "error": (
                        "No data source provided and Google Calendar API not configured. "
                        "Upload an .ics file or paste an iCal URL."
                    ),
                    "detail": str(e),
                }), 400

        if events is None:
            return jsonify({"error": "No events loaded"}), 400

        # Run analytics
        results = analyze_events(events, cfg)
        stats = get_summary_stats(results)
        top_people = get_top_participants(results, 25)

        # Build response (aggregate only, no raw PII)
        response = {
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
            "by_type": _serialize_buckets(results["by_type"]),
            "by_day_of_week": _serialize_buckets(results["by_day_of_week"]),
            "duration_distribution": results["duration_distribution"],
            "client_breakdown": _serialize_buckets(results["client_breakdown"]),
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
