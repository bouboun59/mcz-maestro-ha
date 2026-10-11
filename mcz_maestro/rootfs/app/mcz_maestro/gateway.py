"""Passerelle MQTT <-> poêle MCZ Maestro avec découverte automatique Home Assistant."""
from __future__ import annotations

import json
import os
import logging
import queue
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt

from . import protocol as P
from .config import Config
from .transport import CloudTransport, LocalTransport, Transport

_LOG = logging.getLogger("maestro.gateway")
VERSION = os.environ.get("APP_VERSION", "dev")


class Gateway:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        b = cfg.base_topic.rstrip("/")
        self.t_bridge = f"{b}/bridge/status"
        self.t_stove = f"{b}/stove/status"
        self.t_state = f"{b}/state"
        self.t_set = f"{b}/set/"
        self.t_raw = f"{b}/raw_command"
        self.uid = cfg.device_id

        self._cmd_q: "queue.Queue[tuple[int, int] | None]" = queue.Queue()
        self._pending: dict[int, int] = {}        # dédoublonnage : param -> dernière valeur
        self._pending_lock = threading.Lock()
        self._refresh_now = threading.Event()
        self._last_frame = 0.0
        self._connected_at = 0.0
        self._stale_after = max(45.0, cfg.refresh_interval * 3)
        self._stove_online: bool | None = None
        self._last_state: dict[str, Any] = {}
        self._extra: dict[str, Any] = {}
        self._extra_due = 0.0
        self._stop = threading.Event()

        # ---- MQTT
        self.mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                client_id=f"mcz-maestro-ha-{self.uid}")
        if cfg.mqtt_user:
            self.mqtt.username_pw_set(cfg.mqtt_user, cfg.mqtt_password or None)
        self.mqtt.will_set(self.t_bridge, "offline", qos=1, retain=True)
        self.mqtt.on_connect = self._on_mqtt_connect
        self.mqtt.on_message = self._on_mqtt_message
        self.mqtt.reconnect_delay_set(1, 60)

        # ---- transport
        if cfg.connection_mode == "cloud":
            self.transport: Transport = CloudTransport(
                cfg.cloud_url, cfg.cloud_serial, cfg.cloud_mac,
                self._on_frame, self._on_transport_status)
        else:
            self.transport = LocalTransport(
                cfg.local_host, cfg.local_port, self._on_frame, self._on_transport_status)

    # ================================================================== MQTT
    def _on_mqtt_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code.is_failure:
            _LOG.error("MQTT : connexion refusée (%s)", reason_code)
            return
        _LOG.info("MQTT : connecté à %s:%s", self.cfg.mqtt_host, self.cfg.mqtt_port)
        client.publish(self.t_bridge, "online", qos=1, retain=True)
        client.subscribe(f"{self.t_set}#", qos=1)
        client.subscribe(self.t_raw, qos=1)
        if self.cfg.legacy_enabled and self.cfg.legacy_topic_sub:
            client.subscribe(self.cfg.legacy_topic_sub, qos=1)
        client.subscribe(f"{self.cfg.discovery_prefix}/status", qos=1)
        if self.cfg.discovery:
            self.publish_discovery()
        self._publish_stove_status(force=True)
        if self._last_state:
            client.publish(self.t_state, json.dumps(self._last_state), qos=1, retain=True)

    def _on_mqtt_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode(errors="ignore").strip()
        _LOG.info("MQTT << %s : %s", topic, payload)
        try:
            if topic == f"{self.cfg.discovery_prefix}/status":
                if payload == "online" and self.cfg.discovery:
                    self.publish_discovery()
                    self._publish_stove_status(force=True)
                return
            if topic.startswith(self.t_set):
                name = topic[len(self.t_set):]
                if name == "refresh":
                    self._refresh_now.set()
                    return
                cmds = P.build_commands(name, payload, self.cfg.auto_regulation)
            elif topic == self.t_raw or (self.cfg.legacy_enabled and topic == self.cfg.legacy_topic_sub):
                cmds = P.parse_legacy_commands(payload)
            else:
                return
        except KeyError:
            _LOG.warning("Commande inconnue : %s", topic)
            return
        except Exception as err:  # noqa: BLE001
            _LOG.warning("Commande invalide %s=%r (%s)", topic, payload, err)
            return
        for c in cmds:
            self.enqueue(*c)

    # ============================================================ commandes
    def enqueue(self, param: int, value: int) -> None:
        with self._pending_lock:
            already = param in self._pending
            self._pending[param] = value     # la dernière valeur l'emporte (anti-rebond)
        if not already:
            self._cmd_q.put((param, value))

    def _command_worker(self) -> None:
        while not self._stop.is_set():
            item = self._cmd_q.get()
            if item is None:
                return
            param, _ = item
            # attendre que le poêle soit joignable (max 2 min, sinon on abandonne)
            deadline = time.time() + 120
            while not self.transport.connected and time.time() < deadline and not self._stop.is_set():
                time.sleep(1)
            with self._pending_lock:
                value = self._pending.pop(param, None)
            if value is None:
                continue
            msg = P.write_param(param, value)
            if self.transport.send(msg):
                _LOG.info("Poêle >> %s", msg)
            else:
                _LOG.error("Commande perdue (poêle injoignable) : %s", msg)
            time.sleep(self.cfg.command_delay)
            if param >= P.BANK_OFFSET:
                self._extra_due = 0.0          # relire les recettes après écriture
            if self._cmd_q.empty():
                time.sleep(1.0)
                self._refresh_now.set()

    # ============================================================== polling
    def _poller(self) -> None:
        while not self._stop.is_set():
            self._refresh_now.wait(self.cfg.refresh_interval)
            self._refresh_now.clear()
            if self.transport.connected:
                self.transport.send(P.INFO_REQUEST)
                if time.time() >= self._extra_due:   # recettes : au démarrage, après écriture, puis /10 min
                    self._extra_due = time.time() + 600
                    time.sleep(0.5)
                    self.transport.send(P.EXTRA_REQUEST)
                ref = max(self._last_frame, self._connected_at)
                if ref and time.time() - ref > self._stale_after:
                    _LOG.warning("Aucune trame depuis %.0f s, reconnexion", time.time() - ref)
                    self._connected_at = time.time()
                    self.transport.reconnect()
            self._publish_stove_status()

    # ====================================================== trames poêle
    def _on_transport_status(self, connected: bool) -> None:
        # Une coupure brève ne rend pas les entités indisponibles : seule l'absence de trame
        # pendant « unavailable_after » secondes le fait (voir _stove_is_online).
        if connected:
            self._connected_at = time.time()
            self._extra_due = 0.0
            self._refresh_now.set()

    def _on_frame(self, frame: str) -> None:
        if P.is_extra_frame(frame):
            extra = P.parse_extra_frame(frame)
            if extra and extra != self._extra:
                _LOG.info("Recettes : %s", extra)
                self._extra = extra
                if self._last_state:
                    self._last_state.update(extra)
                    self.mqtt.publish(self.t_state, json.dumps(self._last_state), qos=1, retain=True)
            return
        if not P.is_info_frame(frame):
            _LOG.debug("Trame ignorée : %s", str(frame)[:60])
            return
        try:
            modern, legacy = P.parse_info_frame(frame)
        except Exception:  # noqa: BLE001
            _LOG.exception("Trame illisible : %s", frame)
            return
        self._last_frame = time.time()
        modern.update(self._extra)
        modern["connection_mode"] = self.cfg.connection_mode
        modern["last_update"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self._publish_stove_status()

        changed = {k: v for k, v in modern.items()
                   if k != "last_update" and self._last_state.get(k) != v}
        self._last_state = modern
        if changed or not self.cfg.publish_on_change_only:
            self.mqtt.publish(self.t_state, json.dumps(modern), qos=1, retain=True)
            if changed:
                _LOG.debug("État modifié : %s", changed)
        if self.cfg.legacy_enabled and self.cfg.legacy_topic_pub:
            self.mqtt.publish(self.cfg.legacy_topic_pub, json.dumps(legacy), qos=1)

    def _stove_is_online(self) -> bool:
        if self._last_frame == 0.0:
            return False
        return (time.time() - self._last_frame) < self.cfg.unavailable_after

    def _publish_stove_status(self, force: bool = False) -> None:
        online = self._stove_is_online()
        if force or online != self._stove_online:
            self._stove_online = online
            self.mqtt.publish(self.t_stove, "online" if online else "offline", qos=1, retain=True)

    # ============================================================ discovery
    def _device(self) -> dict:
        return {
            "identifiers": [f"mczha_{self.uid}"],
            "name": self.cfg.device_name,
            "manufacturer": "MCZ",
            "model": "Maestro",
            "sw_version": f"MCZ Maestro HA {VERSION} ({self.cfg.connection_mode})",
        }

    def _base(self, component: str, obj: str, name: str | None) -> dict:
        return {
            "unique_id": f"mczha_{self.uid}_{obj}",
            # remplace « object_id » (supprimé depuis HA 2026.4)
            "default_entity_id": f"{component}.{self.cfg.entity_prefix}_{obj}",
            "name": name,
            "device": self._device(),
            "availability": [{"topic": self.t_bridge}, {"topic": self.t_stove}],
            "availability_mode": "all",
            "origin": {"name": "MCZ Maestro HA", "sw_version": VERSION,
                       "support_url": "https://github.com/bouboun59/mcz-maestro-ha"},
        }

    def _disc(self, component: str, obj: str, name: str | None, **extra) -> None:
        cfg = self._base(component, obj, name)
        cfg.update(extra)
        topic = f"{self.cfg.discovery_prefix}/{component}/mczha_{self.uid}/{obj}/config"
        self.mqtt.publish(topic, json.dumps(cfg), qos=1, retain=True)

    def _vt(self, key: str) -> str:
        return "{{ value_json.%s }}" % key

    def publish_discovery(self) -> None:
        st, s = self.t_state, self.t_set
        _LOG.info("Publication de la découverte MQTT Home Assistant")

        # ---- Climate
        self._disc(
            "climate", "climate", None,
            modes=["off", "heat"],
            mode_state_topic=st, mode_state_template=self._vt("hvac_mode"),
            mode_command_topic=f"{s}hvac_mode",
            action_topic=st, action_template=self._vt("hvac_action"),
            current_temperature_topic=st, current_temperature_template=self._vt("ambient_temperature"),
            temperature_state_topic=st, temperature_state_template=self._vt("setpoint"),
            temperature_command_topic=f"{s}setpoint",
            fan_modes=P.FAN_OPTIONS,
            fan_mode_state_topic=st, fan_mode_state_template=self._vt("fan_ambient_mode"),
            fan_mode_command_topic=f"{s}fan_ambient",
            min_temp=self.cfg.min_temp, max_temp=self.cfg.max_temp,
            temp_step=0.5, precision=0.5, temperature_unit="C", optimistic=False,
            icon="mdi:fireplace",
        )

        # ---- Switches
        switches = [
            ("power", "Marche", "power", "power", "mdi:power", None),
            ("eco", "Mode Eco", "eco_mode_sw", "eco", "mdi:leaf", None),
            ("silent", "Mode Silence", "silent_mode_sw", "silent", "mdi:volume-off", None),
            ("active", "Mode Active", "active_mode_sw", "active", "mdi:fire-circle", "config"),
            ("chrono", "Chronothermostat", "chronostat_sw", "chrono", "mdi:calendar-clock", None),
            ("sound", "Effets sonores", "sound_effects_sw", "sound", "mdi:music", "config"),
            ("summer", "Mode été", "summer_sw", "summer", "mdi:weather-sunny", "config"),
            ("antifreeze", "Antigel", "antifreeze_sw", "antifreeze", "mdi:snowflake", "config"),
        ]
        for obj, name, key, cmd, icon, cat in switches:
            extra = {"entity_category": cat} if cat else {}
            self._disc("switch", obj, name, state_topic=st, value_template=self._vt(key),
                       command_topic=f"{s}{cmd}", payload_on="ON", payload_off="OFF",
                       state_on="ON", state_off="OFF", icon=icon, **extra)

        # ---- Selects
        self._disc("select", "power_level", "Puissance", state_topic=st,
                   value_template="{{ value_json.power_level | string }}",
                   command_topic=f"{s}power_level", options=["1", "2", "3", "4", "5"],
                   icon="mdi:fire")
        self._disc("select", "air_recipe", "Recette air", state_topic=st,
                   value_template=self._vt("air_recipe"), command_topic=f"{s}air_recipe",
                   options=P.AIR_RECIPE_OPTIONS, icon="mdi:weather-windy", entity_category="config")
        self._disc("select", "pellet_recipe", "Recette granulés", state_topic=st,
                   value_template=self._vt("pellet_recipe"), command_topic=f"{s}pellet_recipe",
                   options=P.PELLET_RECIPE_OPTIONS, icon="mdi:grain", entity_category="config")
        self._disc("select", "regulation", "Régulation", state_topic=st,
                   value_template=self._vt("regulation"), command_topic=f"{s}regulation",
                   options=["auto", "manual"], icon="mdi:thermostat-auto")
        fans = [("fan_ambient", "Ventilation ambiance")]
        if self.cfg.ducted_fans >= 1:
            fans.append(("fan_ducted1", "Ventilation canalisée 1"))
        if self.cfg.ducted_fans >= 2:
            fans.append(("fan_ducted2", "Ventilation canalisée 2"))
        for key, name in fans:
            self._disc("select", key, name, state_topic=st, value_template=self._vt(f"{key}_mode"),
                       command_topic=f"{s}{key}", options=P.FAN_OPTIONS, icon="mdi:fan")
        for key in ("fan_ducted1", "fan_ducted2")[self.cfg.ducted_fans:]:
            self._remove("select", key)

        # ---- Number (consigne, pratique pour les automatisations / cartes)
        self._disc("number", "setpoint", "Consigne", state_topic=st, value_template=self._vt("setpoint"),
                   command_topic=f"{s}setpoint", min=self.cfg.min_temp, max=self.cfg.max_temp,
                   step=0.5, unit_of_measurement="°C", device_class="temperature", mode="box",
                   icon="mdi:thermometer")

        # ---- Boutons
        self._disc("button", "reset_alarm", "Acquitter l'alarme", command_topic=f"{s}reset_alarm",
                   payload_press="1", icon="mdi:alarm-light-off", entity_category="config")
        self._disc("button", "refresh", "Rafraîchir", command_topic=f"{s}refresh",
                   payload_press="1", icon="mdi:refresh", entity_category="diagnostic")

        # ---- Capteurs
        temp = {"device_class": "temperature", "unit_of_measurement": "°C", "state_class": "measurement"}
        sensors = [
            ("state", "État", "stove_state", {"icon": "mdi:fireplace"}),
            ("state_code", "Code état", "stove_state_code", {"entity_category": "diagnostic", "icon": "mdi:numeric"}),
            ("ambient_temperature", "Température ambiante", "ambient_temperature", temp),
            ("fumes_temperature", "Température fumées", "fumes_temperature", temp),
            ("motherboard_temperature", "Température carte mère", "motherboard_temperature",
             {**temp, "entity_category": "diagnostic"}),
            ("power_level_live", "Puissance active", "power_level", {"icon": "mdi:fire", "state_class": "measurement"}),
            ("profile", "Profil", "profile", {"icon": "mdi:tune", "value_template":
                "{{ {0:'Manuel',1:'Dynamic',2:'Overnight',3:'Comfort',4:'Power 110%',10:'Adaptatif'}"
                ".get(value_json.profile, value_json.profile) }}"}),
            ("active_set", "Active consigne", "active_set",
             {"icon": "mdi:fire-circle", "state_class": "measurement"}),
            ("active_live", "Active", "active_live",
             {"icon": "mdi:fire-circle", "state_class": "measurement"}),
            ("fumes_fan_rpm", "Extracteur fumées", "fumes_fan_rpm",
             {"unit_of_measurement": "rpm", "state_class": "measurement", "icon": "mdi:fan", "entity_category": "diagnostic"}),
            ("auger_rpm", "Vis sans fin", "auger_rpm_live",
             {"unit_of_measurement": "rpm", "state_class": "measurement", "icon": "mdi:screw-lag", "entity_category": "diagnostic"}),
            ("hours_to_service", "Heures avant entretien", "hours_to_service",
             {"unit_of_measurement": "h", "icon": "mdi:wrench-clock"}),
            ("operating_hours", "Heures de fonctionnement", "operating_hours_total",
             {"unit_of_measurement": "h", "state_class": "total_increasing", "icon": "mdi:timer-outline"}),
            ("ignitions", "Nombre d'allumages", "ignitions",
             {"state_class": "total_increasing", "icon": "mdi:counter"}),
            ("minutes_to_switch_off", "Minutes avant extinction", "minutes_to_switch_off",
             {"unit_of_measurement": "min", "icon": "mdi:timer-sand", "entity_category": "diagnostic"}),
            ("brazier", "Brasero", "brazier", {"icon": "mdi:fire-alert", "entity_category": "diagnostic",
                "value_template": "{{ {0:'OK',100:'Fermeture',101:'Ouverture'}.get(value_json.brazier, value_json.brazier) }}"}),
            ("stove_datetime", "Horloge du poêle", "stove_datetime",
             {"icon": "mdi:clock-outline", "entity_category": "diagnostic"}),
            ("connection_mode", "Mode de connexion", "connection_mode",
             {"icon": "mdi:lan-connect", "entity_category": "diagnostic"}),
        ]
        if self.cfg.hydro:
            sensors += [
                ("boiler_temperature", "Température chaudière", "boiler_temperature", temp),
                ("puffer_temperature", "Température puffer", "puffer_temperature", temp),
                ("return_temperature", "Température retour", "return_temperature", temp),
            ]
            self._disc("number", "boiler_setpoint", "Consigne chaudière", state_topic=st,
                       value_template=self._vt("boiler_setpoint"), command_topic=f"{s}boiler_setpoint",
                       min=30, max=80, step=1, unit_of_measurement="°C", device_class="temperature",
                       mode="box")
        else:
            for obj in ("boiler_temperature", "puffer_temperature", "return_temperature"):
                self._remove("sensor", obj)
            self._remove("number", "boiler_setpoint")

        for obj, name, key, extra in sensors:
            extra = dict(extra)
            vt = extra.pop("value_template", self._vt(key))
            self._disc("sensor", obj, name, state_topic=st, value_template=vt, **extra)

        # ---- Binary sensors
        self._disc("binary_sensor", "running", "En chauffe", state_topic=st, value_template=self._vt("power"),
                   payload_on="ON", payload_off="OFF", device_class="running")
        self._disc("binary_sensor", "alarm", "Alarme", state_topic=st, value_template=self._vt("alarm"),
                   payload_on="ON", payload_off="OFF", device_class="problem")
        self._disc("binary_sensor", "pellet_low", "Pellets bas", state_topic=st,
                   value_template=self._vt("pellet_low"), payload_on="ON", payload_off="OFF",
                   device_class="problem", icon="mdi:grain")
        self._disc("binary_sensor", "igniter", "Bougie", state_topic=st, value_template=self._vt("candle_sw"),
                   payload_on="ON", payload_off="OFF", icon="mdi:lightning-bolt",
                   entity_category="diagnostic")
        # connectivité : sans « availability » pour rester visible quand le poêle est injoignable
        conn = self._base("binary_sensor", "connectivity", "Connexion poêle")
        conn.pop("availability"), conn.pop("availability_mode")
        conn.update(state_topic=self.t_stove, payload_on="online", payload_off="offline",
                    device_class="connectivity", entity_category="diagnostic",
                    availability_topic=self.t_bridge)
        self.mqtt.publish(
            f"{self.cfg.discovery_prefix}/binary_sensor/mczha_{self.uid}/connectivity/config",
            json.dumps(conn), qos=1, retain=True)

    def _remove(self, component: str, obj: str) -> None:
        self.mqtt.publish(f"{self.cfg.discovery_prefix}/{component}/mczha_{self.uid}/{obj}/config",
                          "", qos=1, retain=True)

    # ================================================================= run
    def run(self) -> None:
        _LOG.info("MCZ Maestro HA %s — mode %s", VERSION, self.cfg.connection_mode.upper())
        while True:
            try:
                self.mqtt.connect(self.cfg.mqtt_host, self.cfg.mqtt_port, keepalive=60)
                break
            except Exception as err:  # noqa: BLE001
                _LOG.error("MQTT injoignable (%s:%s) : %s — nouvel essai dans 10 s",
                           self.cfg.mqtt_host, self.cfg.mqtt_port, err)
                time.sleep(10)
        self.mqtt.loop_start()
        threading.Thread(target=self._command_worker, name="commands", daemon=True).start()
        threading.Thread(target=self._poller, name="poller", daemon=True).start()
        self.transport.start()
        try:
            while not self._stop.wait(10):
                self._publish_stove_status()
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self._stop.set()
        self.transport.stop()
        self._cmd_q.put(None)
        try:
            self.mqtt.publish(self.t_bridge, "offline", qos=1, retain=True).wait_for_publish(2)
        except Exception:  # noqa: BLE001
            pass
        self.mqtt.loop_stop()
        self.mqtt.disconnect()
