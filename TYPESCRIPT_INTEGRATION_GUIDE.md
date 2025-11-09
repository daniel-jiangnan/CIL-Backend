# TypeScript/React Frontend Integration Guide

## 📦 Installation

Install required packages in your React project:

```bash
npm install react react-dom
npm install --save-dev typescript @types/react @types/react-dom @types/node
```

## 📋 File Structure

Copy the provided files to your React project:

```
your-react-app/
├── src/
│   ├── api/
│   │   └── appointment-api-client.ts      # API client
│   ├── components/
│   │   └── AppointmentSearch/
│   │       ├── index.tsx
│   │       ├── SearchByDate.tsx
│   │       ├── SearchByCustomer.tsx
│   │       └── AppointmentTable.tsx
│   ├── App.tsx
│   └── ...
```

## 🚀 Quick Start

### 1. Basic Usage

```typescript
import { AppointmentApiClient } from "@/api/appointment-api-client";

const apiClient = new AppointmentApiClient();

// Search by date
const results = await apiClient.searchByDate("2025-12-09");
console.log(`Found ${results.count} appointments`);

// Search by customer
const customerResults = await apiClient.searchByCustomer(
  "John",
  "Doe",
  "2025-12-09",
  "housing"
);
```

### 2. Simple React Component

```typescript
import { useState } from "react";
import { AppointmentApiClient } from "@/api/appointment-api-client";

export function SimpleSearch() {
  const [date, setDate] = useState("2025-12-09");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  const apiClient = new AppointmentApiClient();

  const handleSearch = async () => {
    setLoading(true);
    try {
      const data = await apiClient.searchByDate(date);
      setResults(data);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input
        type="date"
        value={date}
        onChange={(e) => setDate(e.target.value)}
      />
      <button onClick={handleSearch} disabled={loading}>
        {loading ? "Searching..." : "Search"}
      </button>

      {results && (
        <div>
          <h3>Found {results.count} appointments</h3>
          <ul>
            {results.appointments.map((appt, idx) => (
              <li key={idx}>
                {appt.time} - {appt.event_summary}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

### 3. Use Provided Components

```typescript
import { AppointmentSearchContainer } from "@/components/AppointmentSearch";

export default function App() {
  return (
    <div>
      <h1>CIL Appointment System</h1>
      <AppointmentSearchContainer />
    </div>
  );
}
```

## 📝 Complete Component Examples

### Search by Date Component

```typescript
import { useState } from "react";
import { AppointmentApiClient } from "@/api/appointment-api-client";
import type { SearchByDateResponse } from "@/api/appointment-api-client";

export function SearchByDateComponent() {
  const [date, setDate] = useState(new Date().toISOString().split("T")[0]);
  const [results, setResults] = useState<SearchByDateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apiClient = new AppointmentApiClient();

  const handleSearch = async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await apiClient.searchByDate(date);
      setResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="search-container">
      <h2>Search Appointments by Date</h2>

      <div className="search-form">
        <label>
          Date:
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            disabled={loading}
          />
        </label>
        <button onClick={handleSearch} disabled={loading}>
          {loading ? "Searching..." : "Search"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {results && (
        <div className="results">
          <h3>
            {results.date} - Total: {results.count} appointments
          </h3>
          {results.appointments.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Event</th>
                  <th>Attendee</th>
                  <th>Email</th>
                </tr>
              </thead>
              <tbody>
                {results.appointments.map((appt, idx) => (
                  <tr key={idx}>
                    <td>{appt.time}</td>
                    <td>{appt.event_summary}</td>
                    <td>{appt.attendee_name}</td>
                    <td>{appt.attendee_email || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p>No appointments found</p>
          )}
        </div>
      )}
    </div>
  );
}
```

### Search by Customer Component

```typescript
import { useState } from "react";
import { AppointmentApiClient } from "@/api/appointment-api-client";
import type { SearchByCustomerResponse } from "@/api/appointment-api-client";

interface CustomerForm {
  firstName: string;
  lastName: string;
  date: string;
  service: string;
}

export function SearchByCustomerComponent() {
  const [form, setForm] = useState<CustomerForm>({
    firstName: "",
    lastName: "",
    date: new Date().toISOString().split("T")[0],
    service: "",
  });
  const [results, setResults] = useState<SearchByCustomerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apiClient = new AppointmentApiClient();

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSearch = async () => {
    if (!form.firstName || !form.lastName || !form.service) {
      setError("Please fill in all required fields");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await apiClient.searchByCustomer(
        form.firstName,
        form.lastName,
        form.date,
        form.service
      );
      setResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="search-container">
      <h2>Search Appointments by Customer</h2>

      <div className="search-form">
        <label>
          First Name:
          <input
            type="text"
            name="firstName"
            value={form.firstName}
            onChange={handleInputChange}
            disabled={loading}
          />
        </label>

        <label>
          Last Name:
          <input
            type="text"
            name="lastName"
            value={form.lastName}
            onChange={handleInputChange}
            disabled={loading}
          />
        </label>

        <label>
          Date:
          <input
            type="date"
            name="date"
            value={form.date}
            onChange={handleInputChange}
            disabled={loading}
          />
        </label>

        <label>
          Service Type:
          <input
            type="text"
            name="service"
            value={form.service}
            onChange={handleInputChange}
            placeholder="e.g., housing, peer support"
            disabled={loading}
          />
        </label>

        <button onClick={handleSearch} disabled={loading}>
          {loading ? "Searching..." : "Search"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {results && (
        <div className="results">
          <h3>
            {results.customer_name} - {results.search_date} - {results.count}{" "}
            appointment(s)
          </h3>
          {results.appointments.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Event</th>
                  <th>Attendee</th>
                  <th>Email</th>
                </tr>
              </thead>
              <tbody>
                {results.appointments.map((appt, idx) => (
                  <tr key={idx}>
                    <td>{appt.time}</td>
                    <td>{appt.event_summary}</td>
                    <td>{appt.attendee_name}</td>
                    <td>{appt.attendee_email || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p>No matching appointments found</p>
          )}
        </div>
      )}
    </div>
  );
}
```

## 🛠️ Custom API Client URL

If your API runs on a different address:

```typescript
// Method 1: Specify when instantiating
const apiClient = new AppointmentApiClient("http://your-api-server:8000");

// Method 2: Use environment variables
const apiClient = new AppointmentApiClient(
  process.env.REACT_APP_API_URL || "http://localhost:8000"
);
```

**.env file:**

```
REACT_APP_API_URL=http://your-production-api.com
```

## 📡 Error Handling Best Practices

```typescript
try {
  const results = await apiClient.searchByCustomer(
    firstName,
    lastName,
    date,
    service
  );
} catch (error) {
  if (error instanceof Error) {
    if (error.message.includes("Invalid date format")) {
      setError("Date format is incorrect");
    } else if (error.message.includes("timeout")) {
      setError("Request timed out, please retry");
    } else {
      setError(error.message);
    }
  } else {
    setError("An unknown error occurred");
  }
}
```

## 📊 Using React Query (Recommended for Production)

```typescript
import { useQuery } from "@tanstack/react-query";
import { AppointmentApiClient } from "@/api/appointment-api-client";

const apiClient = new AppointmentApiClient();

export const useSearchByDate = (date: string) => {
  return useQuery({
    queryKey: ["appointments", "by-date", date],
    queryFn: () => apiClient.searchByDate(date),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
};

export const useSearchByCustomer = (
  firstName: string,
  lastName: string,
  date: string,
  service: string
) => {
  return useQuery({
    queryKey: [
      "appointments",
      "by-customer",
      firstName,
      lastName,
      date,
      service,
    ],
    queryFn: () =>
      apiClient.searchByCustomer(firstName, lastName, date, service),
    enabled: !!firstName && !!lastName && !!service,
    staleTime: 5 * 60 * 1000,
  });
};

// Usage in component
export function MyComponent() {
  const { data, isLoading, error } = useSearchByDate("2025-12-09");

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error: {error.message}</div>;

  return <div>Found {data?.count} appointments</div>;
}
```

## 💾 Caching Strategy

```typescript
class CachedAppointmentApiClient extends AppointmentApiClient {
  private cache = new Map<string, { data: any; timestamp: number }>();
  private cacheDuration = 5 * 60 * 1000; // 5 minutes

  private getCacheKey(endpoint: string, body?: any): string {
    return `${endpoint}:${JSON.stringify(body || {})}`;
  }

  private isCacheValid(timestamp: number): boolean {
    return Date.now() - timestamp < this.cacheDuration;
  }

  // Override request method to add caching logic
  // Implementation details...
}
```

## 📚 Resources

- [Full API Documentation](./API_DOCUMENTATION.md)
- [TypeScript Type Definitions](./appointment-api-client.ts)
- [React Best Practices](https://react.dev/)
- [Fetch API Reference](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API)

---

## 🧪 Testing

Run Swagger UI in browser for interactive API testing:

```
http://localhost:8000/docs
```
