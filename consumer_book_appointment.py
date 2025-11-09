from datetime import datetime, time, timedelta
from typing import List, Dict
import os
import json
import tempfile

from zoneinfo import ZoneInfo  # Python 3.9+
from google.oauth2 import service_account
from googleapiclient.discovery import build


# === Configuration ===
SERVICE_ACCOUNT_FILE = os.getenv(
    "SERVICE_ACCOUNT_FILE", "center-for-independent-living-95cb120a7f0e.json"
)
SERVICE_ACCOUNTS_JSON = os.getenv(
    "SERVICE_ACCOUNTS_JSON", None
)  # JSON string with all service account credentials
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


def load_service_accounts_from_file(txt_file: str) -> List[str]:
    """
    Load service account file paths from a text file
    Each line should contain one path to a service account JSON file

    Args:
        txt_file: Path to text file containing service account paths

    Returns:
        List of service account file paths
    """
    account_files = []
    try:
        with open(txt_file, "r") as f:
            for line in f:
                path = line.strip()
                if path and not path.startswith("#"):  # Skip empty lines and comments
                    account_files.append(path)
        print(f"📋 Loaded {len(account_files)} service account(s) from {txt_file}")
    except FileNotFoundError:
        print(f"❌ File not found: {txt_file}")
    except Exception as e:
        print(f"❌ Error reading file {txt_file}: {e}")

    return account_files


def load_service_accounts_from_env() -> List[str]:
    """
    Load service account credentials from environment variable SERVICE_ACCOUNTS_JSON

    Expected format:
    SERVICE_ACCOUNTS_JSON='[
      {"path": "org1.json", "content": {...}},
      {"path": "org2.json", "content": {...}}
    ]'

    Returns:
        List of service account file paths created from environment variable
    """
    if not SERVICE_ACCOUNTS_JSON:
        return []

    try:
        accounts_data = json.loads(SERVICE_ACCOUNTS_JSON)
        account_files = []

        for account in accounts_data:
            path = account.get("path")
            content = account.get("content")

            if path and content:
                # Create temporary directory if needed
                os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(
                    path
                ) else None

                # Write credential JSON to file
                with open(path, "w") as f:
                    json.dump(content, f)

                account_files.append(path)
                print(f"✅ Loaded service account from environment: {path}")

        return account_files

    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse SERVICE_ACCOUNTS_JSON: {e}")
        return []
    except Exception as e:
        print(f"❌ Error loading service accounts from environment: {e}")
        return []


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
    service_account_file: str | List[str],
    calendar_ids_file: str = "calendars.json",
) -> List[Dict]:
    """
    Retrieve all appointments for a specific date (for admin viewing)

    Args:
        target_date: The date to search for appointments (datetime object)
        service_account_file:
            - Single service account JSON file path (str)
            - List of service account JSON file paths (List[str])
            - Path to a .txt file containing service account paths (str ending with .txt)
        calendar_ids_file: Path to JSON file containing calendar IDs (default: "calendars.json")

    Returns:
        List of all appointments on that date with details
    """
    try:
        # Handle different input formats
        if isinstance(service_account_file, str):
            if service_account_file.endswith(".txt"):
                # Load from txt file
                account_files = load_service_accounts_from_file(service_account_file)
            else:
                # Single JSON file
                account_files = [service_account_file]
        else:
            # Already a list
            account_files = service_account_file

        # If no account files found and SERVICE_ACCOUNTS_JSON env var is set, load from there
        if not account_files and SERVICE_ACCOUNTS_JSON:
            account_files = load_service_accounts_from_env()

        if not account_files:
            print(
                "⚠️  No service accounts found. Please set SERVICE_ACCOUNTS_JSON env var or provide account files."
            )
            return []

        # Load calendar IDs from config file
        calendar_ids = load_calendar_ids_from_file(calendar_ids_file)

        target_date_obj = (
            target_date.date() if isinstance(target_date, datetime) else target_date
        )

        print("📅 Searching for appointments on date:")
        print(f"   Date: {target_date_obj}")
        print(
            f"   Searching {len(account_files)} service account(s) with {len(calendar_ids)} calendar(s)..."
        )

        # Collect appointments from all service accounts
        all_appointments = []
        time_min = datetime.combine(target_date_obj, time.min).replace(tzinfo=LOCAL_TZ)
        time_max = datetime.combine(
            target_date_obj + timedelta(days=1), time.min
        ).replace(tzinfo=LOCAL_TZ)

        for account_file in account_files:
            try:
                # Create service with provided account file
                creds = service_account.Credentials.from_service_account_file(
                    account_file, scopes=SCOPES
                )
                service_api = build("calendar", "v3", credentials=creds)

                # If no calendar IDs specified, try to get them from CalendarList
                calendars_to_poll = calendar_ids if calendar_ids else []

                if not calendars_to_poll:
                    try:
                        calendar_list_response = (
                            service_api.calendarList().list().execute()
                        )
                        calendars_to_poll = [
                            item["id"]
                            for item in calendar_list_response.get("items", [])
                        ]
                        print(
                            f"   📅 {account_file}: {len(calendars_to_poll)} calendar(s) from CalendarList"
                        )
                    except Exception as e:
                        print(f"⚠️  Error listing calendars for {account_file}: {e}")
                        continue
                else:
                    print(
                        f"   📅 {account_file}: Using {len(calendars_to_poll)} configured calendar(s)"
                    )

                # Poll all calendars for this service account
                for calendar_id in calendars_to_poll:
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
                                        "service_account": account_file,
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
                                    "service_account": account_file,
                                }
                                all_appointments.append(appointment)

                    except Exception as e:
                        print(
                            f"⚠️  Error polling calendar {calendar_id} from {account_file}: {e}"
                        )

            except Exception as e:
                print(f"❌ Error with service account {account_file}: {e}")

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
    service_account_file: str | List[str],
    calendar_ids_file: str = "calendars.json",
) -> List[Dict]:
    """
    Retrieve matched appointments based on customer details

    Polls all accessible calendars from one or multiple service accounts
    and finds appointments matching:
    - Customer name (first_name + last_name)
    - Start time (date matching)
    - Service type

    Args:
        first_name: Customer's first name
        last_name: Customer's last name
        start_time: Appointment start time (datetime object)
        service: Service type to match
        service_account_file:
            - Single service account JSON file path (str)
            - List of service account JSON file paths (List[str])
            - Path to a .txt file containing service account paths (str ending with .txt)
        calendar_ids_file: Path to JSON file containing calendar IDs (default: "calendars.json")

    Returns:
        List of matched appointments with details
    """
    try:
        # Handle different input formats
        if isinstance(service_account_file, str):
            if service_account_file.endswith(".txt"):
                # Load from txt file
                account_files = load_service_accounts_from_file(service_account_file)
            else:
                # Single JSON file
                account_files = [service_account_file]
        else:
            # Already a list
            account_files = service_account_file

        # If no account files found and SERVICE_ACCOUNTS_JSON env var is set, load from there
        if not account_files and SERVICE_ACCOUNTS_JSON:
            account_files = load_service_accounts_from_env()

        if not account_files:
            print(
                "⚠️  No service accounts found. Please set SERVICE_ACCOUNTS_JSON env var or provide account files."
            )
            return []

        # Load calendar IDs from config file
        calendar_ids = load_calendar_ids_from_file(calendar_ids_file)

        print("🔍 Searching for appointments:")
        print(f"   Name: {first_name} {last_name}")
        print(f"   Date: {start_time.date()}")
        print(f"   Service: {service}")
        print(
            f"   Searching {len(account_files)} service account(s) with {len(calendar_ids)} calendar(s)..."
        )

        # Collect appointments from all service accounts
        all_appointments = []
        today = datetime.now(LOCAL_TZ).date()
        time_min = datetime.combine(today, time.min).replace(tzinfo=LOCAL_TZ)
        time_max = datetime.combine(today + timedelta(days=90), time.min).replace(
            tzinfo=LOCAL_TZ
        )

        for account_file in account_files:
            try:
                # Create service with provided account file
                creds = service_account.Credentials.from_service_account_file(
                    account_file, scopes=SCOPES
                )
                service_api = build("calendar", "v3", credentials=creds)

                # If no calendar IDs specified, try to get them from CalendarList
                calendars_to_poll = calendar_ids if calendar_ids else []

                if not calendars_to_poll:
                    try:
                        calendar_list_response = (
                            service_api.calendarList().list().execute()
                        )
                        calendars_to_poll = [
                            item["id"]
                            for item in calendar_list_response.get("items", [])
                        ]
                        print(
                            f"   📅 {account_file}: {len(calendars_to_poll)} calendar(s) from CalendarList"
                        )
                    except Exception as e:
                        print(f"⚠️  Error listing calendars for {account_file}: {e}")
                        continue
                else:
                    print(
                        f"   📅 {account_file}: Using {len(calendars_to_poll)} configured calendar(s)"
                    )

                # Poll all calendars for this service account
                for calendar_id in calendars_to_poll:
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
                                    "service_account": account_file,
                                }
                                all_appointments.append(appointment)

                    except Exception as e:
                        print(
                            f"⚠️  Error polling calendar {calendar_id} from {account_file}: {e}"
                        )

            except Exception as e:
                print(f"❌ Error with service account {account_file}: {e}")

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
