"""Google Calendar API authentication."""

import os
import pickle
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_calendar_service(credentials_file: str = "credentials.json",
                         token_file: str = "token.json"):
    """Authenticate and return a Google Calendar API service object.

    Uses OAuth 2.0 with offline access. On first run, opens a browser
    for authorization. Subsequent runs use the stored token.
    """
    creds = None
    token_path = Path(token_file)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(credentials_file).exists():
                raise FileNotFoundError(
                    f"'{credentials_file}' not found.\n\n"
                    "To set up Google Calendar API access:\n"
                    "1. Go to https://console.cloud.google.com/apis/credentials\n"
                    "2. Create an OAuth 2.0 Client ID (Desktop application)\n"
                    "3. Download the JSON and save it as 'credentials.json'\n"
                    "4. Enable the Google Calendar API in your project\n"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file, SCOPES
            )
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds)
