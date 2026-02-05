"""Fetch events from Google Calendar API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from dateutil.relativedelta import relativedelta


def fetch_events(service, calendar_id: str = "primary",
                 start_date: Optional[datetime] = None,
                 end_date: Optional[datetime] = None,
                 max_results: int = 2500) -> list[dict]:
    """Fetch calendar events within a date range.

    Args:
        service: Google Calendar API service object.
        calendar_id: Calendar ID to query.
        start_date: Start of range (defaults to 1 year ago).
        end_date: End of range (defaults to now).
        max_results: Maximum events per API page.

    Returns:
        List of event dictionaries from the API.
    """
    now = datetime.now(timezone.utc)

    if start_date is None:
        start_date = now - relativedelta(years=1)
    if end_date is None:
        end_date = now

    time_min = start_date.isoformat()
    time_max = end_date.isoformat()

    all_events = []
    page_token = None

    while True:
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token,
        ).execute()

        events = result.get("items", [])
        all_events.extend(events)

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return all_events


def parse_event(event: dict) -> Optional[dict]:
    """Parse a raw API event into a normalized dictionary.

    Skips all-day events (no dateTime field) since they aren't
    typical meetings.

    Returns:
        Parsed event dict or None if it should be skipped.
    """
    start_raw = event.get("start", {})
    end_raw = event.get("end", {})

    # Skip all-day events
    if "dateTime" not in start_raw:
        return None

    start_dt = datetime.fromisoformat(start_raw["dateTime"])
    end_dt = datetime.fromisoformat(end_raw["dateTime"])
    duration_minutes = (end_dt - start_dt).total_seconds() / 60

    # Skip events with zero or negative duration
    if duration_minutes <= 0:
        return None

    attendees = []
    for att in event.get("attendees", []):
        attendees.append({
            "email": att.get("email", ""),
            "name": att.get("displayName", ""),
            "response": att.get("responseStatus", "needsAction"),
            "organizer": att.get("organizer", False),
            "self": att.get("self", False),
        })

    return {
        "id": event.get("id", ""),
        "summary": event.get("summary", "(No title)"),
        "description": event.get("description", ""),
        "start": start_dt,
        "end": end_dt,
        "duration_minutes": duration_minutes,
        "attendees": attendees,
        "attendee_count": len(attendees),
        "organizer_email": event.get("organizer", {}).get("email", ""),
        "status": event.get("status", "confirmed"),
        "recurring": event.get("recurringEventId") is not None,
        "hangout_link": event.get("hangoutLink", ""),
        "location": event.get("location", ""),
    }


def get_parsed_events(service, calendar_id: str = "primary",
                       start_date: Optional[datetime] = None,
                       end_date: Optional[datetime] = None) -> list[dict]:
    """Fetch and parse all events in the given range."""
    raw_events = fetch_events(service, calendar_id, start_date, end_date)
    parsed = []
    for event in raw_events:
        p = parse_event(event)
        if p is not None:
            parsed.append(p)
    return parsed
