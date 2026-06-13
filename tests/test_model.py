from backend.model import Model


def reading(**overrides):
    value = {
        "temperature": 32.0,
        "humidity": 70.0,
        "gas": 1000,
        "temperature_abnormal": False,
        "gas_abnormal": False,
        "has_problem": False,
    }
    value.update(overrides)
    return value


def test_notification_is_created_only_on_transition() -> None:
    first = Model._transition_notifications(reading(gas=2100, gas_abnormal=True), None)
    continuous = Model._transition_notifications(
        reading(gas=2200, gas_abnormal=True),
        reading(gas=2100, gas_abnormal=True),
    )

    assert [item["notification_type"] for item in first] == ["gas"]
    assert continuous == []


def test_dht_problem_does_not_create_temperature_notification() -> None:
    notifications = Model._transition_notifications(
        reading(temperature=0, humidity=0, has_problem=True),
        reading(),
    )

    assert [item["notification_type"] for item in notifications] == ["data_problem"]
