"""Classify meetings as internal, client, or external."""

from __future__ import annotations

from enum import Enum


class MeetingType(str, Enum):
    INTERNAL = "internal"
    CLIENT = "client"
    EXTERNAL = "external"
    SOLO = "solo"  # Only you, no other attendees


def classify_meeting(event: dict, config: dict) -> MeetingType:
    """Classify a meeting based on attendees and title.

    Classification logic (in priority order):
    1. Solo: No attendees or only yourself
    2. Internal: All attendees share a company domain
    3. Client: Any attendee has a known client domain, OR title
       contains client keywords
    4. External: Attendees from non-company, non-client domains

    Args:
        event: Parsed event dictionary from fetcher.
        config: Configuration dictionary with company_domains,
                client_domains, and keyword lists.

    Returns:
        MeetingType enum value.
    """
    company_domains = set(d.lower() for d in config.get("company_domains", []))
    client_domains = {k.lower(): v for k, v in config.get("client_domains", {}).items()}
    client_keywords = [k.lower() for k in config.get("client_title_keywords", [])]
    internal_keywords = [k.lower() for k in config.get("internal_title_keywords", [])]

    attendees = event.get("attendees", [])
    title = event.get("summary", "").lower()

    # Filter out resource rooms and self
    real_attendees = [
        a for a in attendees
        if not a.get("self", False)
        and not a.get("email", "").endswith("calendar.google.com")
        and a.get("email", "") != ""
    ]

    if len(real_attendees) == 0:
        return MeetingType.SOLO

    # Classify each attendee's domain
    attendee_domains = set()
    has_company = False
    has_client = False
    has_external = False

    for att in real_attendees:
        email = att.get("email", "").lower()
        domain = email.split("@")[-1] if "@" in email else ""
        attendee_domains.add(domain)

        if domain in company_domains:
            has_company = True
        elif domain in client_domains:
            has_client = True
        else:
            has_external = True

    # All non-self attendees are from company domains
    if has_company and not has_client and not has_external:
        return MeetingType.INTERNAL

    # At least one known client domain
    if has_client:
        return MeetingType.CLIENT

    # Check title for client keywords
    if any(kw in title for kw in client_keywords):
        return MeetingType.CLIENT

    # Check title for internal keywords
    if any(kw in title for kw in internal_keywords):
        return MeetingType.INTERNAL

    return MeetingType.EXTERNAL


def get_attendee_domains(event: dict) -> dict[str, list[str]]:
    """Extract unique domains and associated emails from attendees."""
    domains: dict[str, list[str]] = {}
    for att in event.get("attendees", []):
        email = att.get("email", "").lower()
        if not email or email.endswith("calendar.google.com") or att.get("self"):
            continue
        domain = email.split("@")[-1] if "@" in email else ""
        if domain:
            domains.setdefault(domain, []).append(email)
    return domains


def identify_client_for_event(event: dict, config: dict) -> str | None:
    """Return the client name if the event involves a known client domain."""
    client_domains = {k.lower(): v for k, v in config.get("client_domains", {}).items()}
    for att in event.get("attendees", []):
        email = att.get("email", "").lower()
        domain = email.split("@")[-1] if "@" in email else ""
        if domain in client_domains:
            return client_domains[domain]
    return None
