from dataclasses import replace
from datetime import date

import pytest

from backend.config import settings
from backend.sistem import PayloadError, Sistem, validate_payload


class FakeModel:
    def latest_reading(self):
        return None


def test_valid_payload_matches_esp32_rule() -> None:
    reading = validate_payload(
        {"temperature": 32.4, "humidity": 74, "gas": 1840, "buzzer": "OFF"}
    )

    assert reading["temperature_abnormal"] is False
    assert reading["gas_abnormal"] is False
    assert reading["buzzer_inconsistent"] is False


@pytest.mark.parametrize(
    ("temperature", "is_abnormal"),
    [(29, True), (29.1, False), (38.9, False), (39, True)],
)
def test_temperature_boundaries(temperature: float, is_abnormal: bool) -> None:
    reading = validate_payload(
        {"temperature": temperature, "humidity": 70, "gas": 1000, "buzzer": "ON" if is_abnormal else "OFF"}
    )
    assert reading["temperature_abnormal"] is is_abnormal


@pytest.mark.parametrize(("gas", "is_abnormal"), [(2000, False), (2001, True)])
def test_gas_boundary(gas: int, is_abnormal: bool) -> None:
    reading = validate_payload(
        {"temperature": 32, "humidity": 70, "gas": gas, "buzzer": "ON" if is_abnormal else "OFF"}
    )
    assert reading["gas_abnormal"] is is_abnormal


def test_paired_zero_marks_dht_problem_without_temperature_abnormal() -> None:
    reading = validate_payload(
        {"temperature": 0, "humidity": 0, "gas": 1500, "buzzer": "ON"}
    )

    assert reading["has_problem"] is True
    assert reading["temperature_abnormal"] is False
    assert reading["buzzer_inconsistent"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"temperature": True, "humidity": 70, "gas": 1000, "buzzer": "OFF"},
        {"temperature": 32, "humidity": 101, "gas": 1000, "buzzer": "OFF"},
        {"temperature": 32, "humidity": 70, "gas": 4096, "buzzer": "OFF"},
        {"temperature": 32, "humidity": 70, "gas": 1000, "buzzer": "INVALID"},
        '{"temperature":',
    ],
)
def test_invalid_payloads_are_rejected(payload) -> None:
    with pytest.raises(PayloadError):
        validate_payload(payload)


def test_report_range_is_limited_and_timezone_aware() -> None:
    sistem = Sistem(FakeModel(), replace(settings, display_timezone="Asia/Jakarta"))

    start, end = sistem.parse_report_range("2026-06-13", "2026-06-13")
    assert start.isoformat() == "2026-06-12T17:00:00+00:00"
    assert end.isoformat() == "2026-06-13T17:00:00+00:00"

    with pytest.raises(PayloadError):
        sistem.parse_report_range("2026-06-01", "2026-06-08")
