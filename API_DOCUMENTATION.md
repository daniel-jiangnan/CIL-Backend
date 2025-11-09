# CIL Appointment Search API Documentation

## 📋 Overview

This is a Google Calendar-based appointment search API that provides two main functions:

1. **Search by Date** - Admin view to see all appointments on a specific date
2. **Search by Customer** - Find matching appointments based on customer information

## 🚀 API Base Information

- **Base URL**: `http://localhost:8000`
- **Documentation**: `http://localhost:8000/docs` (Interactive Swagger UI)
- **API Specification**: `http://localhost:8000/openapi.json`

## 🏥 Health Check

### Endpoint

```
GET /health
```

### Response Example

```json
{
  "status": "ok",
  "message": "CIL Appointment API is running"
}
```

---

## Endpoint 1: Search Appointments by Date (Admin View)

Query **all appointments** for a specific date (including all attendees)

### HTTP Method

```
POST /api/appointments/by-date
```

### Request Body

```json
{
  "target_date": "2025-12-09",
  "service_account_file": "service_accounts.txt",
  "calendar_ids_file": "calendars.json"
}
```

**Parameters:**

| Parameter              | Type   | Required | Description                                                        |
| ---------------------- | ------ | -------- | ------------------------------------------------------------------ |
| `target_date`          | string | ✅       | Date in format: `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SS`              |
| `service_account_file` | string | ❌       | Service account config file path (default: `service_accounts.txt`) |
| `calendar_ids_file`    | string | ❌       | Calendar IDs config file path (default: `calendars.json`)          |

### Response Example

**Success (200 OK):**

```json
{
  "success": true,
  "message": "Found 2 appointment(s) on 2025-12-09",
  "date": "2025-12-09",
  "count": 2,
  "appointments": [
    {
      "event_id": "abc123",
      "calendar_id": "cal@group.calendar.google.com",
      "event_summary": "Housing appointment",
      "attendee_email": "user@gmail.com",
      "attendee_name": "user@gmail.com",
      "datetime": "2025-12-09T00:00:00-08:00",
      "date": "2025-12-09",
      "time": "00:00:00",
      "service_account": "service-account.json"
    }
  ]
}
```

### cURL Example

```bash
curl -X POST http://localhost:8000/api/appointments/by-date \
  -H "Content-Type: application/json" \
  -d '{"target_date": "2025-12-09"}'
```

### JavaScript Example

```javascript
const response = await fetch("http://localhost:8000/api/appointments/by-date", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ target_date: "2025-12-09" }),
});
const data = await response.json();
```

---

## Endpoint 2: Search Appointments by Customer Information

Find matching appointments based on customer name, date, and service type

### HTTP Method

```
POST /api/appointments/by-customer
```

### Request Body

```json
{
  "first_name": "dzhang",
  "last_name": "1601",
  "appointment_date": "2025-12-09",
  "service": "housing",
  "service_account_file": "service_accounts.txt",
  "calendar_ids_file": "calendars.json"
}
```

**Parameters:**

| Parameter              | Type   | Required | Description                                              |
| ---------------------- | ------ | -------- | -------------------------------------------------------- |
| `first_name`           | string | ✅       | Customer's first name (partial match supported)          |
| `last_name`            | string | ✅       | Customer's last name (partial match supported)           |
| `appointment_date`     | string | ✅       | Date: `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SS`              |
| `service`              | string | ✅       | Service type (e.g., "housing", "peer support")           |
| `service_account_file` | string | ❌       | Service account config (default: `service_accounts.txt`) |
| `calendar_ids_file`    | string | ❌       | Calendar IDs config (default: `calendars.json`)          |

**Matching Rules:**

- Name: Flexible matching, ignores spaces and case
- Date: Exact match only
- Service: Fuzzy substring match

### Response Example

**Success (200 OK):**

```json
{
  "success": true,
  "message": "Found 1 appointment(s) for dzhang 1601",
  "customer_name": "dzhang 1601",
  "search_date": "2025-12-09",
  "service": "housing",
  "count": 1,
  "appointments": [
    {
      "event_id": "abc123",
      "calendar_id": "cal@group.calendar.google.com",
      "event_summary": "Housing appointment",
      "attendee_email": "user@gmail.com",
      "attendee_name": "user@gmail.com",
      "datetime": "2025-12-09T00:00:00-08:00",
      "date": "2025-12-09",
      "time": "00:00:00",
      "service_account": "service-account.json"
    }
  ]
}
```

### cURL Example

```bash
curl -X POST http://localhost:8000/api/appointments/by-customer \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "dzhang",
    "last_name": "1601",
    "appointment_date": "2025-12-09",
    "service": "housing"
  }'
```

---

## Response Fields

### Appointment Object

```json
{
  "event_id": "unique-id", // Google Calendar event ID
  "calendar_id": "cal@group.calendar.google.com", // Calendar identifier
  "event_summary": "Housing appointment", // Appointment name
  "attendee_email": "user@gmail.com", // Attendee email address
  "attendee_name": "user name", // Attendee display name
  "datetime": "2025-12-09T00:00:00-08:00", // ISO 8601 date-time
  "date": "2025-12-09", // Date only (YYYY-MM-DD)
  "time": "00:00:00", // Time only (HH:MM:SS)
  "service_account": "account-file.json" // Service account used
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Description                      |
| ---- | -------------------------------- |
| 200  | Success                          |
| 400  | Bad request (invalid parameters) |
| 500  | Server error                     |

### Error Response

```json
{
  "detail": "Invalid date format. Use 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SS'"
}
```

---

## Configuration Files

### service_accounts.txt

```
center-for-independent-living-95cb120a7f0e.json
# One service account JSON file path per line
# Lines starting with # are comments
```

### calendars.json

```json
{
  "calendars": [
    {
      "id": "calendar-id@group.calendar.google.com",
      "name": "Calendar Name"
    }
  ]
}
```

---

## Testing

Open Swagger UI in your browser:

```
http://localhost:8000/docs
```

All endpoints can be tested interactively here!

---

## Troubleshooting

1. Verify server is running on `http://localhost:8000`
2. Check `service_accounts.txt` and `calendars.json` exist and are valid
3. Ensure Google Calendar API is properly configured
4. Check service account has access to the calendars
