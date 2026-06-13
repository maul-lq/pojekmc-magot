from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = _env_int("MYSQL_PORT", 3306)
    mysql_database: str = os.getenv("MYSQL_DATABASE", "db_mocom_maggot")
    mysql_user: str = os.getenv("MYSQL_USER", "root")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "admin")

    mqtt_host: str = os.getenv("MQTT_HOST", "192.168.18.43")
    mqtt_port: int = _env_int("MQTT_PORT", 1883)
    mqtt_topic: str = os.getenv("MQTT_TOPIC", "esp32/sensor_data")
    mqtt_username: str = os.getenv("MQTT_USERNAME", "")
    mqtt_password: str = os.getenv("MQTT_PASSWORD", "")
    mqtt_tls: bool = _env_bool("MQTT_TLS")
    mqtt_enabled: bool = _env_bool("MQTT_ENABLED", True)

    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    session_token_pepper: str = os.getenv("SESSION_TOKEN_PEPPER", "")
    session_lifetime_hours: int = _env_int("SESSION_LIFETIME_HOURS", 8)
    cookie_secure: bool = _env_bool("COOKIE_SECURE")
    app_origin: str = os.getenv("APP_ORIGIN", "http://127.0.0.1:8000")

    display_timezone: str = os.getenv("DISPLAY_TIMEZONE", "Asia/Jakarta")
    stale_after_seconds: int = _env_int("STALE_AFTER_SECONDS", 10)
    data_retention_days: int = _env_int("DATA_RETENTION_DAYS", 90)

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.display_timezone)


settings = Settings()
