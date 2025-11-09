from datetime import datetime, time, timedelta
from typing import List, Dict
import os
import json

from zoneinfo import ZoneInfo  # Python 3.9+
from google.oauth2 import service_account
from googleapiclient.discovery import build


# === Configuration ===
SERVICE_ACCOUNT_FILE = os.getenv(
    "SERVICE_ACCOUNT_FILE", "center-for-independent-living-95cb120a7f0e.json"
)
# New format: {calendar_email: credentials_json}
CALENDAR_CREDENTIALS = os.getenv("CALENDAR_CREDENTIALS", None)
SCOPES = ["https://www.googleapis.com/auth/calendar"]

LOCAL_TZ = ZoneInfo("America/Los_Angeles")
WORK_START = time(9, 0)
WORK_END = time(18, 0)


# === Build the Calendar API client ===
def get_calendar_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build("calendar", "v3", credentials=creds)
    return service


# === Core Appointment Functions ===


def get_credentials_for_calendar(calendar_email: str):
    """
    Get service account credentials for a specific calendar email

    Expected environment variable format:
    CALENDAR_CREDENTIALS='{
      "calendar@group.calendar.google.com": {
        "type": "service_account",
        "project_id": "...",
        "private_key": "...",
        ...
      }
    }'

    Args:
        calendar_email: Calendar email address (e.g., "abc@group.calendar.google.com")

    Returns:
        service_account.Credentials object or None if not found
    """
    if not CALENDAR_CREDENTIALS:
        print("⚠️  CALENDAR_CREDENTIALS environment variable not set")
        return None

    try:
        credentials_map = json.loads(CALENDAR_CREDENTIALS)

        if calendar_email not in credentials_map:
            print(f"⚠️  No credentials found for calendar: {calendar_email}")
            return None

        creds_dict = credentials_map[calendar_email]

        # Create credentials from dictionary
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=SCOPES
        )
        print(f"✅ Loaded credentials for calendar: {calendar_email}")
        return creds

    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse CALENDAR_CREDENTIALS: {e}")
        return None
    except Exception as e:
        print(f"❌ Error loading credentials for {calendar_email}: {e}")
        return None


def load_calendar_ids_from_file(json_file: str = "calendars.json") -> List[str]:
    """
    Load calendar IDs from a JSON configuration file

    Args:
        json_file: Path to JSON file containing calendar configuration

    Returns:
        List of calendar IDs
    """
    import json
    import os

    calendar_ids = []
    try:
        if os.path.exists(json_file):
            with open(json_file, "r") as f:
                config = json.load(f)
                for cal in config.get("calendars", []):
                    calendar_ids.append(cal["id"])
            print(f"📋 Loaded {len(calendar_ids)} calendar ID(s) from {json_file}")
        else:
            print(f"⚠️  Calendar config file not found: {json_file}")
    except Exception as e:
        print(f"❌ Error reading calendar config: {e}")

    return calendar_ids


def get_appointments_by_date(
    target_date: datetime,
    service_account_file: str | List[str] = None,
    calendar_ids_file: str = "calendars.json",
) -> List[Dict]:
    """
    Retrieve all appointments for a specific date (for admin viewing)

    Now uses CALENDAR_CREDENTIALS environment variable:
    {
      "calendar@group.calendar.google.com": {credentials_json},
      ...
    }

    Args:
        target_date: The date to search for appointments (datetime object)
        service_account_file: Deprecated - kept for backward compatibility
        calendar_ids_file: Path to JSON file containing calendar IDs (default: "calendars.json")

    Returns:
        List of all appointments on that date with details
    """
    try:
        # Load calendar IDs from config file
        calendar_ids = load_calendar_ids_from_file(calendar_ids_file)

        if not calendar_ids:
            print("⚠️  No calendar IDs found")
            return []

        target_date_obj = (
            target_date.date() if isinstance(target_date, datetime) else target_date
        )

        print("📅 Searching for appointments on date:")
        print(f"   Date: {target_date_obj}")
        print(f"   Searching {len(calendar_ids)} calendar(s)...")

        # Collect appointments from all calendars
        all_appointments = []
        time_min = datetime.combine(target_date_obj, time.min).replace(tzinfo=LOCAL_TZ)
        time_max = datetime.combine(
            target_date_obj + timedelta(days=1), time.min
        ).replace(tzinfo=LOCAL_TZ)

        # Process each calendar
        for calendar_id in calendar_ids:
            try:
                # Get credentials for this specific calendar
                creds = get_credentials_for_calendar(calendar_id)
                if not creds:
                    print(f"⚠️  Skipping {calendar_id} - no credentials")
                    continue

                service_api = build("calendar", "v3", credentials=creds)

                # Query events from this calendar
                try:
                    events_result = (
                        service_api.events()
                        .list(
                            calendarId=calendar_id,
                            timeMin=time_min.isoformat(),
                            timeMax=time_max.isoformat(),
                            singleEvents=True,
                            orderBy="startTime",
                        )
                        .execute()
                    )

                    events = events_result.get("items", [])

                    for event in events:
                        event_id = event.get("id")
                        summary = event.get("summary", "")
                        start_time_str = event["start"].get(
                            "dateTime", event["start"].get("date")
                        )

                        if "T" in start_time_str:
                            appointment_datetime = datetime.fromisoformat(
                                start_time_str.replace("Z", "+00:00")
                            )
                        else:
                            appointment_datetime = datetime.fromisoformat(
                                start_time_str
                            ).replace(tzinfo=LOCAL_TZ)

                        attendees = event.get("attendees", [])

                        # Add event even without attendees for admin view
                        if attendees:
                            for attendee in attendees:
                                appointment = {
                                    "event_id": event_id,
                                    "calendar_id": calendar_id,
                                    "event_summary": summary,
                                    "attendee_email": attendee.get("email"),
                                    "attendee_name": attendee.get(
                                        "displayName", attendee.get("email", "")
                                    ),
                                    "datetime": appointment_datetime,
                                    "date": appointment_datetime.date(),
                                    "time": appointment_datetime.time(),
                                    "service_account": calendar_id,  # Use calendar_id as identifier
                                }
                                all_appointments.append(appointment)
                        else:
                            # Event without attendees
                            appointment = {
                                "event_id": event_id,
                                "calendar_id": calendar_id,
                                "event_summary": summary,
                                "attendee_email": None,
                                "attendee_name": "No attendee",
                                "datetime": appointment_datetime,
                                "date": appointment_datetime.date(),
                                "time": appointment_datetime.time(),
                                "service_account": calendar_id,  # Use calendar_id as identifier
                            }
                            all_appointments.append(appointment)

                except Exception as e:
                    print(f"⚠️  Error polling calendar {calendar_id}: {e}")

            except Exception as e:
                print(f"❌ Error with calendar {calendar_id}: {e}")

        # Sort by time
        all_appointments.sort(key=lambda x: x["time"])

        print(f"\n✅ Found {len(all_appointments)} appointment(s) on {target_date_obj}")
        return all_appointments

    except Exception as e:
        print(f"❌ Error retrieving appointments: {e}")
        import traceback

        traceback.print_exc()
        return []


def get_matched_appointments(
    first_name: str,
    last_name: str,
    start_time: datetime,
    service: str,
    service_account_file: str | List[str] = None,
    calendar_ids_file: str = "calendars.json",
) -> List[Dict]:
    """
    Retrieve matched appointments based on customer details

    Now uses CALENDAR_CREDENTIALS environment variable

    Args:
        first_name: Customer's first name
        last_name: Customer's last name
        start_time: Appointment start time (datetime object)
        service: Service type to match
        service_account_file: Deprecated - kept for backward compatibility
        calendar_ids_file: Path to JSON file containing calendar IDs (default: "calendars.json")

    Returns:
        List of matched appointments with details
    """
    try:
        # Load calendar IDs from config file
        calendar_ids = load_calendar_ids_from_file(calendar_ids_file)

        if not calendar_ids:
            print("⚠️  No calendar IDs found")
            return []

        print("🔍 Searching for appointments:")
        print(f"   Name: {first_name} {last_name}")
        print(f"   Date: {start_time.date()}")
        print(f"   Service: {service}")
        print(f"   Searching {len(calendar_ids)} calendar(s)...")

        # Collect appointments from all calendars
        all_appointments = []
        today = datetime.now(LOCAL_TZ).date()
        time_min = datetime.combine(today, time.min).replace(tzinfo=LOCAL_TZ)
        time_max = datetime.combine(today + timedelta(days=90), time.min).replace(
            tzinfo=LOCAL_TZ
        )

        # Process each calendar
        for calendar_id in calendar_ids:
            try:
                # Get credentials for this specific calendar
                creds = get_credentials_for_calendar(calendar_id)
                if not creds:
                    print(f"⚠️  Skipping {calendar_id} - no credentials")
                    continue

                service_api = build("calendar", "v3", credentials=creds)

                # Query events from this calendar
                try:
                    events_result = (
                        service_api.events()
                        .list(
                            calendarId=calendar_id,
                            timeMin=time_min.isoformat(),
                            timeMax=time_max.isoformat(),
                            singleEvents=True,
                            orderBy="startTime",
                        )
                        .execute()
                    )

                    events = events_result.get("items", [])

                    for event in events:
                        event_id = event.get("id")
                        summary = event.get("summary", "")
                        start_time_str = event["start"].get(
                            "dateTime", event["start"].get("date")
                        )

                        if "T" in start_time_str:
                            appointment_datetime = datetime.fromisoformat(
                                start_time_str.replace("Z", "+00:00")
                            )
                        else:
                            appointment_datetime = datetime.fromisoformat(
                                start_time_str
                            ).replace(tzinfo=LOCAL_TZ)

                        attendees = event.get("attendees", [])

                        for attendee in attendees:
                            appointment = {
                                "event_id": event_id,
                                "calendar_id": calendar_id,
                                "event_summary": summary,
                                "attendee_email": attendee.get("email"),
                                "attendee_name": attendee.get(
                                    "displayName", attendee.get("email", "")
                                ),
                                "datetime": appointment_datetime,
                                "date": appointment_datetime.date(),
                                "time": appointment_datetime.time(),
                                "service_account": calendar_id,  # Use calendar_id as identifier
                            }
                            all_appointments.append(appointment)

                except Exception as e:
                    print(f"⚠️  Error polling calendar {calendar_id}: {e}")

            except Exception as e:
                print(f"❌ Error with calendar {calendar_id}: {e}")

        # Match appointments
        full_name = f"{first_name} {last_name}".strip().lower()
        full_name_no_space = full_name.replace(" ", "")  # Remove spaces for matching
        target_date = start_time.date()
        service_lower = service.lower()

        matched = []
        for appt in all_appointments:
            appt_name = appt["attendee_name"].lower() if appt["attendee_name"] else ""
            appt_name_no_space = appt_name.replace(
                " ", ""
            )  # Remove spaces for matching
            appt_service = (
                appt["event_summary"].lower() if appt["event_summary"] else ""
            )
            appt_date = appt["date"]

            # Match name (flexible - check if names match with or without spaces)
            name_match = (
                full_name in appt_name
                or appt_name in full_name
                or full_name_no_space in appt_name_no_space
                or appt_name_no_space in full_name_no_space
            )

            # Match date
            date_match = appt_date == target_date

            # Match service (flexible - substring match)
            service_match = (
                service_lower in appt_service or appt_service in service_lower
            )

            if name_match and date_match and service_match:
                matched.append(appt)

        print(f"\n✅ Found {len(matched)} matched appointment(s)")
        return matched

    except Exception as e:
        print(f"❌ Error retrieving appointments: {e}")
        import traceback

        traceback.print_exc()
        return []
