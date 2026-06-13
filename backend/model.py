from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.config import Settings, settings
from backend.konektor import Konektor


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(100) NOT NULL UNIQUE,
        password_hash VARCHAR(512) NOT NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        last_login_at DATETIME(6) NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        user_id BIGINT UNSIGNED NOT NULL,
        token_hash CHAR(64) NOT NULL UNIQUE,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        expires_at DATETIME(6) NOT NULL,
        INDEX idx_sessions_expires_at (expires_at),
        CONSTRAINT fk_sessions_user
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sensor_readings (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        temperature DECIMAL(6,2) NOT NULL,
        humidity DECIMAL(6,2) NOT NULL,
        gas INT UNSIGNED NOT NULL,
        buzzer ENUM('ON', 'OFF') NOT NULL,
        temperature_abnormal BOOLEAN NOT NULL DEFAULT FALSE,
        gas_abnormal BOOLEAN NOT NULL DEFAULT FALSE,
        has_problem BOOLEAN NOT NULL DEFAULT FALSE,
        buzzer_inconsistent BOOLEAN NOT NULL DEFAULT FALSE,
        received_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        INDEX idx_readings_received_at (received_at),
        INDEX idx_readings_abnormal (temperature_abnormal, gas_abnormal, has_problem)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        sensor_reading_id BIGINT UNSIGNED NOT NULL,
        notification_type VARCHAR(40) NOT NULL,
        severity ENUM('warning', 'danger') NOT NULL,
        message VARCHAR(255) NOT NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        INDEX idx_notifications_created_at (created_at),
        CONSTRAINT fk_notifications_reading
            FOREIGN KEY (sensor_reading_id) REFERENCES sensor_readings(id)
            ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
)


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Model:
    def __init__(self, db: Konektor | None = None, config: Settings = settings) -> None:
        self.db = db or Konektor(config)
        self.config = config

    def initialize_schema(self) -> None:
        self.db.execute_many(SCHEMA_STATEMENTS)

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        return self.db.fetch_one(
            "SELECT id, username, password_hash, created_at, last_login_at "
            "FROM users WHERE username = %s",
            (username,),
        )

    def create_user(self, username: str, password_hash: str) -> int:
        user_id = self.db.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
            (username, password_hash),
        )
        if user_id is None:
            raise RuntimeError("MySQL tidak mengembalikan id pengguna baru.")
        return user_id

    def update_last_login(self, user_id: int) -> None:
        self.db.execute(
            "UPDATE users SET last_login_at = %s WHERE id = %s",
            (utc_now_naive(), user_id),
        )

    def create_session(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        self.db.execute(
            "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
            (user_id, token_hash, expires_at.replace(tzinfo=None)),
        )

    def get_user_by_session(self, token_hash: str) -> dict[str, Any] | None:
        return self.db.fetch_one(
            """
            SELECT u.id, u.username, u.last_login_at, s.expires_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = %s AND s.expires_at > %s
            """,
            (token_hash, utc_now_naive()),
        )

    def delete_session(self, token_hash: str) -> None:
        self.db.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))

    def cleanup_expired_sessions(self) -> None:
        self.db.execute("DELETE FROM sessions WHERE expires_at <= %s", (utc_now_naive(),))

    def cleanup_old_data(self) -> None:
        cutoff = utc_now_naive() - timedelta(days=self.config.data_retention_days)
        self.db.execute("DELETE FROM sensor_readings WHERE received_at < %s", (cutoff,))

    def latest_reading(self) -> dict[str, Any] | None:
        return self.db.fetch_one(
            "SELECT * FROM sensor_readings ORDER BY received_at DESC, id DESC LIMIT 1"
        )

    def insert_reading(self, reading: dict[str, Any]) -> int:
        previous = self.latest_reading()
        notifications = self._transition_notifications(reading, previous)

        with self.db.transaction() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO sensor_readings (
                        temperature, humidity, gas, buzzer,
                        temperature_abnormal, gas_abnormal, has_problem,
                        buzzer_inconsistent, received_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        reading["temperature"],
                        reading["humidity"],
                        reading["gas"],
                        reading["buzzer"],
                        reading["temperature_abnormal"],
                        reading["gas_abnormal"],
                        reading["has_problem"],
                        reading["buzzer_inconsistent"],
                        reading.get("received_at", utc_now_naive()),
                    ),
                )
                reading_id = cursor.lastrowid
                if reading_id is None:
                    raise RuntimeError("MySQL tidak mengembalikan id pembacaan sensor.")
                for notification in notifications:
                    cursor.execute(
                        """
                        INSERT INTO notifications (
                            sensor_reading_id, notification_type, severity, message
                        ) VALUES (%s, %s, %s, %s)
                        """,
                        (
                            reading_id,
                            notification["notification_type"],
                            notification["severity"],
                            notification["message"],
                        ),
                    )
                return reading_id
            finally:
                cursor.close()

    @staticmethod
    def _transition_notifications(
        reading: dict[str, Any], previous: dict[str, Any] | None
    ) -> list[dict[str, str]]:
        transitions: list[dict[str, str]] = []
        checks = (
            (
                "temperature_abnormal",
                "temperature",
                "danger",
                f"Suhu abnormal terdeteksi: {reading['temperature']:.1f} °C.",
            ),
            (
                "gas_abnormal",
                "gas",
                "danger",
                f"Nilai gas melewati ambang: {reading['gas']}.",
            ),
            (
                "has_problem",
                "data_problem",
                "warning",
                "Pembacaan DHT22 bermasalah atau gagal.",
            ),
        )
        for flag, notification_type, severity, message in checks:
            current_active = bool(reading[flag])
            previous_active = bool(previous and previous.get(flag))
            if current_active and not previous_active:
                transitions.append(
                    {
                        "notification_type": notification_type,
                        "severity": severity,
                        "message": message,
                    }
                )
        return transitions

    def readings(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 120,
        offset: int = 0,
        ascending: bool = False,
    ) -> list[dict[str, Any]]:
        where, params = self._range_clause(start, end)
        order = "ASC" if ascending else "DESC"
        sql = (
            "SELECT * FROM sensor_readings "
            f"{where} ORDER BY received_at {order}, id {order} LIMIT %s OFFSET %s"
        )
        return self.db.fetch_all(sql, (*params, limit, offset))

    def count_readings(self, start: datetime, end: datetime) -> int:
        where, params = self._range_clause(start, end)
        row = self.db.fetch_one(
            f"SELECT COUNT(*) AS total FROM sensor_readings {where}", params
        )
        return int(row["total"] if row else 0)

    def notifications(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            "SELECT * FROM notifications ORDER BY created_at DESC, id DESC LIMIT %s",
            (limit,),
        )

    def statistics(self, start: datetime, end: datetime) -> dict[str, Any]:
        return self.db.fetch_one(
            """
            SELECT
                COUNT(*) AS total_readings,
                MIN(CASE WHEN has_problem = 0 THEN temperature END) AS temperature_min,
                MAX(CASE WHEN has_problem = 0 THEN temperature END) AS temperature_max,
                AVG(CASE WHEN has_problem = 0 THEN temperature END) AS temperature_avg,
                MIN(CASE WHEN has_problem = 0 THEN humidity END) AS humidity_min,
                MAX(CASE WHEN has_problem = 0 THEN humidity END) AS humidity_max,
                AVG(CASE WHEN has_problem = 0 THEN humidity END) AS humidity_avg,
                MIN(gas) AS gas_min,
                MAX(gas) AS gas_max,
                AVG(gas) AS gas_avg,
                SUM(temperature_abnormal) AS temperature_abnormal_count,
                SUM(gas_abnormal) AS gas_abnormal_count,
                SUM(has_problem) AS dht_problem_count,
                SUM(buzzer = 'ON') AS buzzer_active_count,
                SUM(buzzer_inconsistent) AS buzzer_inconsistent_count
            FROM sensor_readings
            WHERE received_at >= %s AND received_at < %s
            """,
            (start.replace(tzinfo=None), end.replace(tzinfo=None)),
        ) or {}

    def abnormal_events(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            """
            SELECT n.*
            FROM notifications n
            WHERE n.created_at >= %s AND n.created_at < %s
            ORDER BY n.created_at DESC, n.id DESC
            """,
            (start.replace(tzinfo=None), end.replace(tzinfo=None)),
        )

    @staticmethod
    def _range_clause(
        start: datetime | None, end: datetime | None
    ) -> tuple[str, tuple[Any, ...]]:
        clauses: list[str] = []
        params: list[Any] = []
        if start is not None:
            clauses.append("received_at >= %s")
            params.append(start.replace(tzinfo=None))
        if end is not None:
            clauses.append("received_at < %s")
            params.append(end.replace(tzinfo=None))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return where, tuple(params)
