"""Button presses arriving over MQTT, e.g. a Zigbee button paired with zigbee2mqtt.

zigbee2mqtt publishes {"action": "single", ...} on zigbee2mqtt/<button name>
whenever the button is pressed. Any message with a non-empty "action" counts as a press.
"""
import json
import logging
import threading

import paho.mqtt.client as mqtt

import config

log = logging.getLogger(__name__)


class ButtonListener:
    def __init__(self, on_press=None) -> None:
        self.pressed = threading.Event()
        self.presses = 0  # increases with every press; lets callers notice newer presses
        self._on_press = on_press
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._connected
        self.client.on_message = self._message
        self.client.connect_async(config.MQTT_HOST, config.MQTT_PORT)
        self.client.loop_start()  # runs in a background thread, reconnects by itself

    def _connected(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.warning("MQTT connection failed: %s", reason_code)
            return
        for topic in config.BUTTON_TOPICS:
            client.subscribe(topic)
        log.info("Listening for button presses on %s", ", ".join(config.BUTTON_TOPICS))

    def _message(self, client, userdata, msg) -> None:
        try:
            data = json.loads(msg.payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        action = data.get("action") if isinstance(data, dict) else None
        if not action:
            return  # battery / link-quality updates etc.
        log.info("Button %s: %s", msg.topic, action)
        self.presses += 1
        self.pressed.set()
        if self._on_press:
            self._on_press()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for the next press. Returns True if there was one."""
        got = self.pressed.wait(timeout)
        self.pressed.clear()
        return got

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
