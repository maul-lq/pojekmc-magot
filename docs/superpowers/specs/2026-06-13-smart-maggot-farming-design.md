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

The application framework and runtime are fixed as:

- FastAPI for REST endpoints, page serving, and application lifecycle.
- Uvicorn with exactly one worker.
- Paho MQTT for the Mosquitto subscriber.
- `mysql-connector-python` for MySQL access.
- `openpyxl` for Excel export.
- `reportlab` for PDF export.
- Python dependencies recorded in `requirements.txt`.
- Tailwind CSS dependencies and build commands recorded in `package.json`.

The supported startup command is:

```powershell
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000 --workers 1
```

The MQTT subscriber starts once in the FastAPI lifespan and stops during application shutdown. Running multiple Uvicorn workers is not supported because it would create duplicate MQTT subscribers and duplicate stored readings. Future horizontal scaling would require moving MQTT ingestion into a separate service; that is outside this project scope.

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
- `ADMIN_USERNAME` is required at startup. `ADMIN_PASSWORD` is required and must contain at least 12 characters when the configured initial admin does not exist. Startup fails with a clear error if required initial credentials are absent or invalid.
- The password is never stored as plain text. It is hashed with Python's `hashlib.scrypt` using a random per-password salt before insertion into MySQL.
- If the initial username already exists, startup must not overwrite its password.
- Successful login creates a server-side session with a cryptographically random 32-byte opaque token.
- Only a SHA-256 hash of the token combined with the required `SESSION_TOKEN_PEPPER` is stored in MySQL.
- The browser receives the session token only through a cookie with:
  - `HttpOnly`
  - `SameSite=Lax`
  - `Secure` when configured for HTTPS
- The cookie name is `maggot_session`, its path is `/`, and its default lifetime/`Max-Age` is eight hours.
- Expired sessions are rejected and deleted during startup and opportunistically during authentication.
- Login is limited to five failed attempts per 15 minutes for each IP-address and username pair. The rate limiter is in-memory because the supported runtime is a single process.
- Cookie-authenticated state-changing requests validate that `Origin`, when present, matches the configured application origin. Login and logout accept only `POST`.
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
| `buzzer_inconsistent` | Reported buzzer differs from the valid calculated rule |
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

Notifications are created only when a condition transitions from inactive to active. A continuous abnormal condition therefore creates one onset notification, not a notification every two seconds. Separate transitions are tracked for temperature, gas, and DHT data problems. Buzzer state is presented as device status and does not create its own notification.

Sensor readings are retained for 90 days by default. A scheduled daily cleanup inside the single application process deletes older readings, related notifications, and expired sessions. The retention period is configurable, but disabling retention is outside the supported default deployment.

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

- A DHT failure is identified only when both `temperature == 0` and `humidity == 0`, matching the fallback assignment in `Magot.ino`.
- DHT-failure rows are stored for traceability and marked as a problem, but they are excluded from temperature/humidity minimum, maximum, average, and temperature-abnormal counts. They create a data-problem transition notification rather than a temperature notification.
- Gas remains valid and can create a gas-abnormal notification even when the DHT reading failed.
- The reported buzzer value is preserved. When DHT and gas values are valid, it is compared with the calculated ESP32 rule and `buzzer_inconsistent` records any mismatch. A mismatch is shown as a data/device warning but does not replace the reported buzzer value.
- MQTT payload size is limited to 1,024 bytes.
- Missing keys, non-object JSON, boolean sensor values, NaN/infinity, non-numeric sensor values, and buzzer values other than `ON` or `OFF` are rejected and logged.
- Valid physical/input ranges are temperature `-40..80`, humidity `0..100`, and raw MQ gas `0..4095`.
- MQTT ingestion errors must not terminate the API process.

## 9. REST API Contract

The route names below are fixed.

Successful JSON responses use:

```json
{"ok": true, "data": {}}
```

Error responses use:

```json
{
  "ok": false,
  "error": {
    "code": "machine_readable_code",
    "message": "Pesan singkat dalam Bahasa Indonesia",
    "details": {}
  }
}
```

Validation errors return `422`, unauthenticated requests return `401`, forbidden origin requests return `403`, missing resources return `404`, rate-limited login attempts return `429`, and unexpected service/database errors return `503` or `500` as appropriate.

All API timestamps are RFC 3339 UTC strings. Sensor-history results sort newest first.

### Authentication

- `POST /api/auth/login`
  - Accept JSON `{"username": "string", "password": "string"}`.
  - Return success and create session cookie.

- `POST /api/auth/logout`
  - Invalidate current session.

- `GET /api/auth/me`
  - Return the currently authenticated user.

### Monitoring

- `GET /api/sensors/latest`
  - Return latest reading, abnormal flags, data age, and online/stale status.

- `GET /api/sensors/history`
  - Return bounded readings for charts.
  - Accept optional RFC 3339 UTC `start`, `end`, and `limit`.
  - Default `limit` is 120 and maximum `limit` is 2,000.

- `GET /api/dashboard/summary`
  - Return current cards, daily min/max/average values, abnormal counts, latest notifications, and recent readings.

- `GET /api/notifications`
  - Return recent abnormal-condition notifications.
  - Accept optional `limit`; default 20 and maximum 200.

### Reports

- `GET /api/reports/summary`
  - Return statistics and abnormal-event counts for a requested date range.

- `GET /api/reports/readings`
  - Return paginated report-table readings.
  - Accept required `start_date` and `end_date`, plus `page` and `page_size`.
  - Default `page_size` is 100 and maximum is 500.

- `GET /api/reports/export.pdf`
  - Download a sensor report for the requested date range.

- `GET /api/reports/export.xlsx`
  - Download the same report data in Excel format.

JSON endpoints use the consistent success/error envelopes and appropriate HTTP status codes. Successful export endpoints return authenticated binary download responses; export errors use the standard JSON error envelope.

Core response data shapes are fixed as follows:

```json
{
  "latest_reading": {
    "id": 123,
    "temperature": 32.4,
    "humidity": 74.0,
    "gas": 1840,
    "buzzer": "OFF",
    "temperature_abnormal": false,
    "gas_abnormal": false,
    "has_problem": false,
    "buzzer_inconsistent": false,
    "received_at": "2026-06-13T12:00:00Z"
  },
  "data_status": {
    "state": "online",
    "age_seconds": 2,
    "stale_after_seconds": 10
  }
}
```

`GET /api/sensors/latest` returns the fields above. If no reading exists, `latest_reading` is `null` and `data_status.state` is `no_data`. The state becomes `stale` when the latest reading age exceeds the configurable threshold, defaulting to ten seconds.

History and report-reading entries use the same reading fields. History data is returned as `{"readings": [], "count": 0}`. Paginated report readings are returned as:

```json
{
  "readings": [],
  "pagination": {
    "page": 1,
    "page_size": 100,
    "total_items": 0,
    "total_pages": 0
  }
}
```

Dashboard summary data contains `latest_reading`, `data_status`, `today_statistics`, `abnormal_counts`, `notifications`, and `recent_readings`. Report summary data contains `range`, per-sensor `minimum`, `maximum`, and `average`, plus counts for abnormal temperature, abnormal gas, DHT problems, buzzer-active readings, and buzzer inconsistencies. DHT-failure rows are excluded from DHT statistics as previously defined.

Notification data contains `id`, `sensor_reading_id`, `notification_type`, `severity`, `message`, and `created_at`. Authenticated-user data contains only `id`, `username`, and `last_login_at`.

Report endpoints accept `start_date` and `end_date` in `YYYY-MM-DD` using the configured display timezone. Both selected calendar dates are included by translating them to an inclusive UTC start and exclusive UTC end. The default range is today. The maximum report/export range is seven calendar days; larger or reversed ranges return `422`.

PDF exports contain summary data and at most the newest 1,000 detailed readings so the document remains readable. Excel exports may contain all readings in the allowed seven-day range. Export generation must stream or use temporary files rather than retaining large output permanently.

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
- Charts use native SVG or Canvas rendering implemented in project JavaScript, avoiding a runtime CDN dependency.
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
SESSION_TOKEN_PEPPER
```

`ADMIN_PASSWORD` is conditionally required when the configured initial admin does not exist. Optional settings may include session lifetime, stale-data threshold, server host/port, and secure-cookie mode.

Secrets must not be committed to the repository.

Additional supported configuration:

```text
DISPLAY_TIMEZONE=Asia/Jakarta
SESSION_LIFETIME_HOURS=8
STALE_AFTER_SECONDS=10
COOKIE_SECURE=false
APP_ORIGIN=http://127.0.0.1:8000
DATA_RETENTION_DAYS=90
MQTT_USERNAME
MQTT_PASSWORD
MQTT_TLS=false
```

MySQL database `db_mocom_maggot` must already exist and be accessible. The application creates or upgrades its required tables idempotently; it does not create the database itself.

The default MQTT deployment assumes a trusted local network, matching the current empty credentials in `Magot.ino`. If MQTT credentials or TLS are configured, the backend uses them. Production use outside a trusted LAN requires Mosquitto authentication, topic ACLs restricted to `esp32/sensor_data`, and TLS.

All database timestamps are stored in UTC. Display values, “today” boundaries, and report calendar dates use `DISPLAY_TIMEZONE`, defaulting to `Asia/Jakarta`.

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
- A paired zero DHT reading is stored, marked as a problem, excluded from DHT statistics, and does not create a temperature notification.
- Buzzer inconsistencies are recorded without replacing the reported value.
- Notifications are emitted once per inactive-to-active condition transition.
- Login succeeds with the seeded admin credentials.
- Login fails safely with invalid credentials.
- Protected APIs reject unauthenticated requests.
- Sessions can be invalidated by logout.
- MySQL schema initialization is repeatable.
- Date-range summary calculations are correct.
- Date ranges honor display-timezone boundaries and the inclusive-calendar-date contract.
- History pagination, API limits, report range limits, and export bounds are enforced.
- PDF and Excel exports are generated for a known dataset.
- Expired sessions and cookie security flags behave as specified.
- MySQL schema initialization is repeatable and asserted by automated SQL checks.

### Frontend checks

- Login redirect and logout work.
- Dashboard handles no-data, normal, abnormal, stale, and API-error states.
- Monitoring polling updates values without duplicating timers.
- Reports apply date filters and produce download requests.
- Layout is usable on desktop and mobile widths.

### Integration checks

- A sample MQTT payload reaches MySQL and becomes visible through the REST API.
- REST responses reflect the same abnormal logic as `Magot.ino`.
- MQTT reconnect behavior does not terminate the API.
- The documented single-worker startup produces only one MQTT subscriber.
- A temporary MySQL outage produces a controlled error and recovers after connectivity returns.
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
