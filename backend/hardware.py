from __future__ import annotations

import logging
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode

from backend.config import Settings, settings
from backend.sistem import PayloadError, Sistem

logger = logging.getLogger(__name__)


class HardwareMQTT:
    def __init__(self, sistem: Sistem, config: Settings = settings) -> None:
        self.sistem = sistem
        self.config = config
        self.client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id="smart-maggot-backend",
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        if config.mqtt_username:
            self.client.username_pw_set(config.mqtt_username, config.mqtt_password)
        if config.mqtt_tls:
            self.client.tls_set()

    def start(self) -> None:
        if not self.config.mqtt_enabled:
            logger.info("MQTT dinonaktifkan melalui MQTT_ENABLED.")
            return
        logger.info(
            "Menghubungkan MQTT ke %s:%s topic=%s",
            self.config.mqtt_host,
            self.config.mqtt_port,
            self.config.mqtt_topic,
        )
        self.client.connect_async(self.config.mqtt_host, self.config.mqtt_port, keepalive=60)
        self.client.loop_start()

    def stop(self) -> None:
        if not self.config.mqtt_enabled:
            return
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None,
    ) -> None:
        if not reason_code.is_failure:
            client.subscribe(self.config.mqtt_topic, qos=1)
            logger.info("MQTT tersambung dan berlangganan ke %s.", self.config.mqtt_topic)
        else:
            logger.error("MQTT gagal tersambung: %s", reason_code)

    @staticmethod
    def _on_disconnect(
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.DisconnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None,
    ) -> None:
        logger.warning("MQTT terputus: %s. Paho akan mencoba tersambung kembali.", reason_code)

    def _on_message(
        self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage
    ) -> None:
        try:
            reading_id = self.sistem.process_payload(message.payload)
            logger.info("Data sensor tersimpan dengan id=%s.", reading_id)
        except PayloadError as exc:
            logger.warning("Payload MQTT ditolak: %s", exc)
        except Exception:
            logger.exception("Gagal menyimpan payload MQTT.")
