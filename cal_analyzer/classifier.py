"""Classify meetings as internal or external and extract organization names."""

from __future__ import annotations

from enum import Enum


class MeetingType(str, Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"
    SOLO = "solo"
    HOLD = "hold"


def classify_meeting(event: dict, config: dict) -> MeetingType:
    """Classify a meeting based on attendee email domains.

    - Hold: Title contains "hold" (case-insensitive) -- calendar placeholder
    - Solo: No attendees, or only a single company-domain attendee
    - Internal: All attendees are from company domains (2+)
    - External: Any attendee is from a non-company domain
    """
    # Check for hold events first
    summary = event.get("summary", "")
    if "hold" in summary.lower():
        return MeetingType.HOLD

    company_domains = set(d.lower() for d in config.get("company_domains", []))
    attendees = event.get("attendees", [])

    # Filter out resource rooms (keep self -- needed for solo detection)
    real_attendees = [
        a for a in attendees
        if not a.get("email", "").endswith("calendar.google.com")
        and a.get("email", "") != ""
    ]

    if len(real_attendees) == 0:
        return MeetingType.SOLO

    # Check if everyone is from company domains
    company_attendees = []
    external_attendees = []
    for att in real_attendees:
        email = att.get("email", "").lower()
        domain = email.split("@")[-1] if "@" in email else ""
        if domain and domain in company_domains:
            company_attendees.append(att)
        elif domain:
            external_attendees.append(att)

    # Any external attendee -> external meeting
    if external_attendees:
        return MeetingType.EXTERNAL

    # Only one company person on the event -> solo
    if len(company_attendees) <= 1:
        return MeetingType.SOLO

    return MeetingType.INTERNAL


def org_name_from_domain(domain: str, config: dict) -> str:
    """Derive an organization name from an email domain.

    Checks config["organization_names"] for an explicit override first.
    Otherwise strips the TLD and title-cases the remainder.

    Examples:
        greenplanet.org      -> Greenplanet
        hope-foundation.org  -> Hope Foundation
        big.nonprofit.com    -> Big Nonprofit
        acme.co.uk           -> Acme
    """
    domain = domain.lower().strip()
    overrides = {k.lower(): v for k, v in config.get("organization_names", {}).items()}
    if domain in overrides:
        return overrides[domain]

    # Strip common TLDs and multi-part suffixes
    parts = domain.split(".")
    # Remove known TLD suffixes
    tld_parts = {"com", "org", "net", "edu", "gov", "io", "co", "us",
                 "uk", "ca", "au", "de", "fr", "digital", "tech", "dev"}
    # Walk from the right and strip TLD segments
    while len(parts) > 1 and parts[-1] in tld_parts:
        parts.pop()

    name = parts[0] if parts else domain.split(".")[0]
    # Split on hyphens and underscores for readability
    name = name.replace("-", " ").replace("_", " ")
    return name.title()


def get_external_orgs(event: dict, config: dict) -> list[str]:
    """Return a list of external organization names from an event's attendees."""
    company_domains = set(d.lower() for d in config.get("company_domains", []))
    orgs = set()
    for att in event.get("attendees", []):
        email = att.get("email", "").lower()
        if not email or email.endswith("calendar.google.com") or att.get("self"):
            continue
        domain = email.split("@")[-1] if "@" in email else ""
        if domain and domain not in company_domains:
            orgs.add(org_name_from_domain(domain, config))
    return sorted(orgs)
