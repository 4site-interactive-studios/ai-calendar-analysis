"""Import and parse iCal (.ics) files and URLs.

Provides an alternative data source to the Google Calendar API.
All data is processed in-memory only -- nothing is written to disk
to prevent PII persistence.
"""

from __future__ import annotations

import ssl
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request

from icalendar import Calendar


def load_ical_from_file(file_path: str) -> Calendar:
    """Load an iCal calendar from a local .ics file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"iCal file not found: {file_path}")
    if not path.suffix.lower() == ".ics":
        raise ValueError(f"Expected .ics file, got: {path.suffix}")
    with open(path, "rb") as f:
        return Calendar.from_ical(f.read())


def load_ical_from_url(url: str) -> Calendar:
    """Fetch and parse an iCal calendar from a URL.

    Works with public iCal URLs (Google Calendar public URL,
    Outlook published calendars, etc.). Data is read into memory
    only -- nothing is cached to disk.
    """
    ctx = ssl.create_default_context()
    req = Request(url, headers={"User-Agent": "CalendarAnalyzer/1.0"})
    with urlopen(req, context=ctx, timeout=30) as response:
        data = response.read()
    return Calendar.from_ical(data)


def ical_to_parsed_events(cal: Calendar,
                          start_date: Optional[datetime] = None,
                          end_date: Optional[datetime] = None) -> list[dict]:
    """Convert an icalendar Calendar object to the same parsed event
    format used by fetcher.parse_event, so the analytics engine can
    process either data source identically.

    Args:
        cal: Parsed icalendar Calendar object.
        start_date: Filter events starting on or after this date.
        end_date: Filter events ending on or before this date.

    Returns:
        List of event dicts in the same schema as fetcher.parse_event.
    """
    events = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        dtstart = component.get("dtstart")
        dtend = component.get("dtend")
        if dtstart is None or dtend is None:
            continue

        start_dt = dtstart.dt
        end_dt = dtend.dt

        # Skip all-day events (date objects, not datetime)
        if not isinstance(start_dt, datetime):
            continue

        # Ensure timezone-aware for filtering
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        # Apply date filters
        if start_date and start_dt < start_date:
            continue
        if end_date and start_dt > end_date:
            continue

        duration_minutes = (end_dt - start_dt).total_seconds() / 60
        if duration_minutes <= 0:
            continue

        # Parse attendees
        attendees = []
        raw_attendees = component.get("attendee")
        if raw_attendees:
            # Can be a single value or a list
            if not isinstance(raw_attendees, list):
                raw_attendees = [raw_attendees]
            for att in raw_attendees:
                email = str(att).replace("mailto:", "").replace("MAILTO:", "")
                params = att.params if hasattr(att, "params") else {}
                attendees.append({
                    "email": email.lower(),
                    "name": str(params.get("CN", "")),
                    "response": str(params.get("PARTSTAT", "NEEDS-ACTION")).lower(),
                    "organizer": False,
                    "self": False,
                })

        # Parse organizer
        organizer = component.get("organizer")
        organizer_email = ""
        if organizer:
            organizer_email = str(organizer).replace("mailto:", "").replace("MAILTO:", "").lower()
            # Mark organizer in attendee list
            for att in attendees:
                if att["email"] == organizer_email:
                    att["organizer"] = True

        summary = str(component.get("summary", "(No title)"))
        description = str(component.get("description", ""))
        location = str(component.get("location", ""))
        uid = str(component.get("uid", ""))

        # Check for recurrence
        recurring = component.get("rrule") is not None or component.get("recurrence-id") is not None

        events.append({
            "id": uid,
            "summary": summary,
            "description": description,
            "start": start_dt,
            "end": end_dt,
            "duration_minutes": duration_minutes,
            "attendees": attendees,
            "attendee_count": len(attendees),
            "organizer_email": organizer_email,
            "status": str(component.get("status", "CONFIRMED")).lower(),
            "recurring": recurring,
            "hangout_link": "",
            "location": location,
        })

    return events


def get_events_from_ical_file(file_path: str,
                               start_date: Optional[datetime] = None,
                               end_date: Optional[datetime] = None) -> list[dict]:
    """One-shot: load an .ics file and return parsed events."""
    cal = load_ical_from_file(file_path)
    return ical_to_parsed_events(cal, start_date, end_date)


def get_events_from_ical_url(url: str,
                              start_date: Optional[datetime] = None,
                              end_date: Optional[datetime] = None) -> list[dict]:
    """One-shot: fetch an iCal URL and return parsed events."""
    cal = load_ical_from_url(url)
    return ical_to_parsed_events(cal, start_date, end_date)
