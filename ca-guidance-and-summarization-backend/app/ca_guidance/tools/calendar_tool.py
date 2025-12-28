# tools/calendar_tool.py

import logging
from crewai.tools import tool
from typing import Dict
import httpx
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)

# Store access token globally (will be set by the API route)
_access_token_store: Dict[str, str] = {}


def set_access_token(token: str):
    """Set the access token for calendar operations."""
    _access_token_store["token"] = token


def get_access_token() -> str | None:
    """Get the access token for calendar operations."""
    return _access_token_store.get("token")

def clear_access_token():
    """Clear the stored access token (e.g., on user logout)."""
    _access_token_store.clear()

def _extract_date_fragment(text: str) -> str | None:
    """
    Try to extract a date/time-like fragment from a longer sentence.
    Examples it can handle:
      - "Deadline is 31st of December 2025 11:59 PM"
      - "Due date: 1st December 2025"
      - "Submission on 2025-12-01 23:59"
      - "Deadline: 01/12/2025 at 11:59 PM"
    Returns the matched fragment string or None.
    """
    if not text:
        return None

    s = text.strip()

    # Common patterns: ISO, day-month-year, slashes, month-name, etc.
    patterns = [
        # 2025-12-01 23:59, 2025-12-01
        r"\b\d{4}-\d{1,2}-\d{1,2}(?:\s+\d{1,2}:\d{2}(?:\s*[APap][Mm])?)?",
        # 01-12-2025 23:59, 01-12-2025
        r"\b\d{1,2}-\d{1,2}-\d{4}(?:\s+\d{1,2}:\d{2}(?:\s*[APap][Mm])?)?",
        # 01/12/2025 23:59, 01/12/2025
        r"\b\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2}(?:\s*[APap][Mm])?)?",
        # 31st of December 2025 11:59 PM, 1st December 2025, 1 December 2025
        r"\b\d{1,2}(?:st|nd|rd|th)?(?:\s+of)?\s+[A-Za-z]{3,9}\s+\d{4}"
        r"(?:\s+\d{1,2}:\d{2}(?:\s*[APap][Mm])?)?",
        # December 31st 2025 11:59 PM, December 31 2025
        r"\b[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?\s+\d{4}"
        r"(?:\s+\d{1,2}:\d{2}(?:\s*[APap][Mm])?)?",
    ]

    for pattern in patterns:
        match = re.search(pattern, s, flags=re.IGNORECASE)
        if match:
            fragment = match.group(0).strip()
            logger.debug(f"Extracted date fragment '{fragment}' from: {text!r}")
            return fragment

    # If nothing matches, fall back to original (maybe it's already clean)
    return s if s else None


def _parse_date(date_str: str) -> datetime | None:
    """
    Parse various date formats into a datetime object (date only).
    """
    if not date_str:
        return None

    date_str = date_str.strip()

    # Try standard YYYY-MM-DD format first
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        pass

    # Remove ordinal suffixes (st, nd, rd, th)
    date_str_clean = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_str, flags=re.IGNORECASE)

    # Also remove isolated 'of' to handle "31 of December 2025"
    date_str_clean = re.sub(r"\bof\b", " ", date_str_clean, flags=re.IGNORECASE)
    date_str_clean = re.sub(r"\s{2,}", " ", date_str_clean).strip()

    # Try various date formats
    formats = [
        "%d %B %Y",   # "1 December 2025"
        "%B %d %Y",   # "December 1 2025"
        "%B %d, %Y",  # "December 1, 2025"
        "%d %b %Y",   # "1 Dec 2025"
        "%b %d %Y",   # "Dec 1 2025"
        "%b %d, %Y",  # "Dec 1, 2025"
        "%d-%m-%Y",   # "01-12-2025"
        "%d/%m/%Y",   # "01/12/2025"
        "%m/%d/%Y",   # "12/01/2025"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str_clean, fmt)
        except ValueError:
            continue

    logger.warning(f"Could not parse date: {date_str}")
    return None


def _parse_date_or_datetime(deadline_str: str) -> datetime | None:
    """
    Parse a string that may contain:
      - Date only
      - Date + time (24h or 12h with AM/PM)
      - A full sentence that contains a date/time
    Returns a naive datetime (no timezone).
    """
    if not deadline_str:
        return None

    # First, try to extract just the date/time portion from the text
    fragment = _extract_date_fragment(deadline_str)
    if not fragment:
        logger.warning(f"No date-like fragment found in: {deadline_str!r}")
        return None

    s = fragment.strip()
    # Remove ordinal suffixes (1st -> 1, etc.)
    s = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", s, flags=re.IGNORECASE)
    # Remove 'of' to handle "31 of December 2025"
    s = re.sub(r"\bof\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s{2,}", " ", s).strip()

    # Try date + time formats first
    dt_formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %I:%M %p",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y %I:%M %p",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %I:%M %p",
        "%d %B %Y %H:%M",
        "%d %B %Y %I:%M %p",
        "%B %d %Y %H:%M",
        "%B %d %Y %I:%M %p",
        "%d %b %Y %H:%M",
        "%d %b %Y %I:%M %p",
        "%b %d %Y %H:%M",
        "%b %d %Y %I:%M %p",
    ]

    for fmt in dt_formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    # Fall back to pure date parsing
    return _parse_date(s)


@tool
def create_calendar_event(title: str, start_date: str, duration_hours: int = 1) -> str:
    """
    Creates a Google Calendar event for assignment deadlines.

    Args:
        title: The title of the event (e.g., "Submit: [Project Topic]")
        start_date: The deadline. Can be:
            - Only a date (even inside a sentence):
                - "2025-12-01"
                - "Deadline is 31st of December 2025"
            - Date + time:
                - "2025-12-01 23:59"
                - "31st of December 2025 11:59 PM"
                - "Deadline is 31st of December 2025 11:59 PM"
        duration_hours: Duration in hours (default is 1)

    Behavior:
        - If start_date is empty or None -> no event created, returns a message.
        - If only date is found -> defaults time to 23:59.
        - If date + time is found -> uses that exact time.
    """
    access_token = get_access_token()
    if not access_token:
        logger.error("Access token not found")
        return "Access token not found in context. Cannot create event."

    # Handle missing / empty start_date (no deadline case)
    if not start_date or not start_date.strip():
        msg = (
            f"No deadline date/time was provided for '{title}'. "
            f"I did not create a calendar event. "
            f"Please provide a date like '2025-12-01' or "
            f"'31st of December 2025 11:59 PM' if you want it scheduled."
        )
        logger.info(msg)
        return msg

    try:
        # Parse the date or date+time from the given string
        start_dt = _parse_date_or_datetime(start_date)

        if not start_dt:
            return (
                f"Could not parse date/time from: '{start_date}'. "
                f"Please provide a cleaner date string like '2025-12-01', "
                f"'31st of December 2025', or '31st of December 2025 11:59 PM'."
            )

        # If only a date was parsed (00:00:00), default to 23:59 as deadline
        if start_dt.hour == 0 and start_dt.minute == 0 and start_dt.second == 0:
            start_dt = start_dt.replace(hour=23, minute=59, second=0, microsecond=0)

        # End time: duration_hours after start
        end_dt = start_dt + timedelta(hours=duration_hours)

        event_data = {
            "summary": title,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "Asia/Colombo",  # adjust if needed
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "Asia/Colombo",
            },
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        logger.info(f"Creating calendar event: {title} at {start_dt.isoformat()}")
        response = httpx.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            json=event_data,
            headers=headers,
            timeout=10.0,
        )

        if response.status_code in (200, 201):
            result = response.json()
            event_id = result.get("id", "unknown")
            logger.info(f"Successfully created calendar event: {event_id}")
            return (
                f"Successfully scheduled '{title}' for "
                f"{start_dt.strftime('%B %d, %Y at %I:%M %p')}."
            )
        else:
            error_msg = (
                f"Failed to create calendar event. "
                f"Status: {response.status_code}, Response: {response.text}"
            )
            logger.error(error_msg)
            return error_msg

    except Exception as e:
        error_msg = f"An error occurred while creating calendar event: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg
