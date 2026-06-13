# Smart Maggot Farming Monitoring Website Design

**Status:** Approved design  
**Date:** 2026-06-13  
**Project:** `pojekmc-magot`

## 1. Goal

Build a native HTML, JavaScript, and Tailwind CSS monitoring website for a Smart Maggot Farming installation. The system receives readings from an ESP32 through Mosquitto MQTT, stores them in MySQL, and exposes them to authenticated users through a Python REST API.

The application must only represent the hardware that exists:

- DHT22 temperature sensor
- DHT22 humidity sensor
- MQ air-quality/gas sensor
- Buzzer warning status

The application does not include manual harvest or production records. “Laporan Produksi Maggot” means a sensor-based report describing the environmental conditions of the maggot farm.

## 2. Scope

### Included

- Login without public registration
- Protected dashboard, monitoring, report pages, and data APIs
- MQTT ingestion from topic `esp32/sensor_data`
- MySQL persistence in database `db_mocom_maggot`
- Real-time-style monitoring through REST polling every two seconds
- Sensor charts and recent-reading tables
- Notifications for abnormal conditions
- Date-range sensor reports
- PDF and Excel export
- Responsive Tailwind CSS interface matching the provided green farming dashboard reference
- Updated project README with setup and operating instructions

### Excluded

- Interactive learning module
- Public user registration
- Manual harvest or maggot-production data entry
- Sensors or metrics not present in `Magot.ino`
- Browser-to-MQTT communication
- WebSocket updates
- User-configurable abnormal thresholds

## 3. Approved Architecture

Use a single integrated Python application.

The backend:

- Serves native HTML, compiled Tailwind CSS, and JavaScript assets.
- Exposes REST endpoints used by the frontend.
- Runs an MQTT subscriber for Mosquitto.
- Validates and stores sensor payloads in MySQL.
- Creates abnormal-condition notifications.
- Authenticates users using a server-side session represented by an `HttpOnly` cookie.
- Generates PDF and Excel sensor reports.

The frontend:

- Uses separate native HTML pages for login, dashboard, monitoring, and reports.
- Uses JavaScript modules to call the REST API.
- Polls the API every two seconds on monitoring surfaces.
- Does not connect directly to Mosquitto or MySQL.

This integrated approach avoids cross-origin and multi-server complexity while preserving clear internal boundaries.

## 4. System Data Flow

```text
DHT22 + MQ + Buzzer
        |
        v
      ESP32
        |
        | MQTT topic: esp32/sensor_data
        v
     Mosquitto
        |
        v
Python MQTT subscriber
        |
        | validate payload and calculate abnormal flags
        v
      MySQL
        |
        v
Python REST API
        |
        | authenticated polling every 2 seconds
        v
Browser dashboard
```

Expected MQTT payload:

```json
{
  "temperature": 32.4,
  "humidity": 74,
  "gas": 1840,
  "buzzer": "OFF"
}
```

## 5. Backend Responsibilities

Existing backend files should be completed according to their intended responsibilities:

- `backend/api.py`
  - Application entry point
  - Static/page serving
  - REST routes
  - Authentication/session handling
  - Startup and shutdown lifecycle

- `backend/hardware.py`
  - Mosquitto connection and subscription
  - MQTT reconnect behavior
  - Payload decoding and validation
  - Forwarding valid readings to the system layer

- `backend/sistem.py`
  - Abnormal-condition rules
  - Dashboard and report aggregation
  - Notification creation logic
  - Export orchestration

- `backend/model.py`
  - MySQL schema creation
  - User, sensor-reading, notification, and session queries
  - Database row mapping

- `backend/konektor.py`
  - MySQL connection configuration and connection helpers
  - Connection retry/error behavior

New focused files may be created within `backend`, `js`, or `view` when keeping a responsibility separate improves clarity.

## 6. Authentication Design

- There is no registration page or registration API.
- The first admin account is created automatically from:
  - `ADMIN_USERNAME`
  - `ADMIN_PASSWORD`
- The password is never stored as plain text. It is hashed before insertion into MySQL.
- If the initial username already exists, startup must not overwrite its password.
- Successful login creates a server-side session with a random opaque token.
- The browser receives the session token only through a cookie with:
  - `HttpOnly`
  - `SameSite=Lax`
  - `Secure` when configured for HTTPS
- Logout invalidates the server-side session and clears the cookie.
- All page routes except login, and all data/export endpoints, require a valid session.

## 7. MySQL Data Model

Database: `db_mocom_maggot`

### `users`

| Column | Purpose |
|---|---|
| `id` | Primary key |
| `username` | Unique login name |
| `password_hash` | Hashed password |
| `created_at` | Account creation time |
| `last_login_at` | Most recent successful login |

### `sessions`

| Column | Purpose |
|---|---|
| `id` | Primary key |
| `user_id` | Related user |
| `token_hash` | Hash of opaque session token |
| `created_at` | Session creation time |
| `expires_at` | Session expiry time |

### `sensor_readings`

| Column | Purpose |
|---|---|
| `id` | Primary key |
| `temperature` | DHT22 temperature |
| `humidity` | DHT22 humidity |
| `gas` | Raw MQ sensor value |
| `buzzer` | `ON` or `OFF` |
| `temperature_abnormal` | Whether temperature violates ESP32 rule |
| `gas_abnormal` | Whether gas violates ESP32 rule |
| `has_problem` | Invalid/zero DHT reading marker |
| `received_at` | Server receipt timestamp |

Indexes must support recent-reading lookup and date-range reports, especially on `received_at`.

### `notifications`

| Column | Purpose |
|---|---|
| `id` | Primary key |
| `sensor_reading_id` | Related sensor reading |
| `notification_type` | Temperature, gas, buzzer, or data problem |
| `severity` | Warning or danger |
| `message` | User-facing Indonesian message |
| `created_at` | Notification timestamp |

Notifications are created from abnormal readings. Repeated abnormal readings may be grouped or rate-limited in the presentation layer so the dashboard remains readable, while the original sensor readings remain complete.

## 8. Abnormal-Condition Rules

Rules must remain consistent with `Magot.ino`.

```text
temperature is normal only when temperature > 29 and temperature < 39
temperature is abnormal when temperature <= 29 or temperature >= 39
gas is abnormal when gas > 2000
buzzer ON means the ESP32 warning is active
humidity has no abnormal threshold
```

Additional data-quality behavior:

- A DHT reading represented by `0` is stored for traceability and marked as a problem because `Magot.ino` uses zero after a DHT read error.
- Missing keys, non-numeric sensor values, non-object JSON, and buzzer values other than `ON` or `OFF` are rejected and logged.
- MQTT ingestion errors must not terminate the API process.

## 9. REST API Contract

Exact route names may follow existing project conventions, but the implementation must provide the following behavior:

### Authentication

- `POST /api/auth/login`
  - Accept username and password.
  - Return success and create session cookie.

- `POST /api/auth/logout`
  - Invalidate current session.

- `GET /api/auth/me`
  - Return the currently authenticated user.

### Monitoring

- `GET /api/sensors/latest`
  - Return latest reading, abnormal flags, data age, and online/stale status.

- `GET /api/sensors/history`
  - Return bounded readings for charts and tables.
  - Support date range and limit parameters.

- `GET /api/dashboard/summary`
  - Return current cards, daily min/max/average values, abnormal counts, latest notifications, and recent readings.

- `GET /api/notifications`
  - Return recent abnormal-condition notifications.

### Reports

- `GET /api/reports/summary`
  - Return statistics and abnormal-event counts for a requested date range.

- `GET /api/reports/export.pdf`
  - Download a sensor report for the requested date range.

- `GET /api/reports/export.xlsx`
  - Download the same report data in Excel format.

All API responses use a consistent JSON error shape and appropriate HTTP status codes.

## 10. Page and UI Design

The approved visual direction closely follows `Contoh UI.png`:

- Deep-green left sidebar
- Farming/leaf visual identity
- Light green-gray application background
- White cards with rounded corners and subtle shadows
- Green for normal status, orange for warning, and red for danger
- Dense but readable monitoring layout
- Responsive design that collapses the sidebar/navigation on smaller screens

### `view/login.html`

- Centered login card
- Smart Maggot Farming branding
- Username and password fields
- Clear error state
- No registration controls

### `view/dashboard.html`

- Four current-value cards:
  - Temperature
  - Humidity
  - MQ gas value
  - Buzzer status
- Main recent sensor chart
- Latest abnormal notifications
- Today’s sensor summary
- Recent-reading table

### `view/monitor.html`

- Online/stale connection indicator and last-reading age
- Real-time charts for temperature, humidity, and gas
- Current buzzer status
- Recent sensor-reading table
- Automatic two-second polling with an understandable API-unavailable state

### `view/laporan.html`

- Start and end date controls
- Summary statistics:
  - Minimum, maximum, and average temperature
  - Minimum, maximum, and average humidity
  - Minimum, maximum, and average gas value
  - Count of abnormal temperature and gas readings
  - Count of buzzer-active readings
- Sensor report table
- PDF and Excel download buttons

## 11. Frontend Behavior

- `index.html` directs users to login or the authenticated dashboard.
- Shared JavaScript handles:
  - Authenticated fetch requests
  - Redirecting unauthorized users to login
  - Navigation behavior
  - Common number, date, and status formatting
- Page-specific JavaScript handles dashboard, monitoring, report, and login behavior.
- Charts should use a lightweight browser charting approach suitable for native JavaScript. If an external chart library is used, it must be loaded in a clear and documented way and must not replace Tailwind CSS for layout.
- Monitoring requests run every two seconds while the page is visible and stop when it is hidden or unloaded.
- The UI clearly distinguishes:
  - Normal reading
  - Abnormal reading
  - Backend unavailable
  - Sensor data stale/offline
  - No data yet

## 12. Reporting and Export

The report represents sensor conditions, not physical maggot harvest output.

PDF output contains:

- Application title
- Selected date range
- Sensor summary statistics
- Abnormal-condition counts
- A bounded, readable sensor data table
- Export generation timestamp

Excel output contains:

- A summary worksheet
- A sensor-readings worksheet
- An abnormal-events worksheet

Export endpoints require authentication and use the same requested date range as the report page.

## 13. Configuration

Runtime configuration is provided through environment variables, documented in README. Required configuration includes:

```text
MYSQL_HOST
MYSQL_PORT
MYSQL_DATABASE=db_mocom_maggot
MYSQL_USER
MYSQL_PASSWORD
MQTT_HOST
MQTT_PORT=1883
MQTT_TOPIC=esp32/sensor_data
ADMIN_USERNAME
ADMIN_PASSWORD
SESSION_SECRET
```

Optional settings may include session lifetime, stale-data threshold, server host/port, and secure-cookie mode.

Secrets must not be committed to the repository.

## 14. Error Handling and Observability

- Invalid MQTT payloads are logged without being stored.
- Temporary MQTT disconnects trigger reconnect attempts.
- MySQL failures return clear API errors and are logged.
- Export failures return a clear download error without exposing secrets.
- Authentication failures use generic messages that do not reveal whether a username exists.
- The frontend displays concise Indonesian messages for failures.
- Logs include enough context to diagnose ingestion, database, authentication, and export issues without logging passwords or raw session tokens.

## 15. Verification Strategy

### Backend tests

- Payload validation accepts the documented ESP32 payload.
- Payload validation rejects missing, malformed, and invalid values.
- Abnormal temperature boundary tests cover `29`, values between `29` and `39`, and `39`.
- Gas boundary tests cover `2000` and values above `2000`.
- Zero DHT values are stored and marked as problems.
- Login succeeds with the seeded admin credentials.
- Login fails safely with invalid credentials.
- Protected APIs reject unauthenticated requests.
- Sessions can be invalidated by logout.
- MySQL schema initialization is repeatable.
- Date-range summary calculations are correct.
- PDF and Excel exports are generated for a known dataset.

### Frontend checks

- Login redirect and logout work.
- Dashboard handles no-data, normal, abnormal, stale, and API-error states.
- Monitoring polling updates values without duplicating timers.
- Reports apply date filters and produce download requests.
- Layout is usable on desktop and mobile widths.

### Integration checks

- A sample MQTT payload reaches MySQL and becomes visible through the REST API.
- REST responses reflect the same abnormal logic as `Magot.ino`.
- DBHub is used to confirm the final MySQL schema and representative stored rows.

## 16. Completion Criteria

The implementation is complete when:

- All included pages and REST endpoints work behind login.
- MQTT payloads from `Magot.ino` are stored in MySQL.
- Dashboard and monitoring update through two-second REST polling.
- Abnormal conditions match the ESP32 rules.
- Sensor reports can be filtered and exported to PDF and Excel.
- The approved reference-inspired responsive design is implemented.
- README contains setup, environment, MySQL, MQTT, Tailwind build, run, and test instructions.
- Targeted tests and fresh verification checks pass.

