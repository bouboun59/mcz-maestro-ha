"""Chargement de la configuration (/data/options.json + variables d'environnement)."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, fields

OPTIONS_FILE = os.environ.get("MCZ_OPTIONS", "/data/options.json")


@dataclass
class Config:
    connection_mode: str = "local"          # local | cloud
    # local
    local_host: str = "192.168.120.1"
    local_port: int = 81
    # cloud
    cloud_url: str = "http://app.mcz.it:9000"
    cloud_serial: str = ""
    cloud_mac: str = ""
    # comportement
    refresh_interval: float = 15.0
    unavailable_after: float = 180.0       # s sans trame avant de passer les entités « indisponibles »
    command_delay: float = 0.7
    auto_regulation: bool = True
    publish_on_change_only: bool = False
    hydro: bool = False
    ducted_fans: int = 0
    min_temp: float = 5.0
    max_temp: float = 35.0
    # MQTT
    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_password: str = ""
    base_topic: str = "mcz_maestro"
    discovery: bool = True
    discovery_prefix: str = "homeassistant"
    device_name: str = "Poêle MCZ"
    device_id: str = "poele"
    # compatibilité avec l'ancien add-on (JSON Maestro/State + « 34,1;42,21 » sur Maestro/Command)
    legacy_enabled: bool = False
    legacy_topic_pub: str = "Maestro/State"
    legacy_topic_sub: str = "Maestro/Command"
    log_level: str = "info"

    @property
    def entity_prefix(self) -> str:
        return f"mcz_maestro_{self.device_id}"

    def validate(self) -> None:
        self.connection_mode = self.connection_mode.lower()
        if self.connection_mode not in ("local", "cloud"):
            raise ValueError("connection_mode doit valoir 'local' ou 'cloud'")
        if self.connection_mode == "cloud" and (not self.cloud_serial or not self.cloud_mac):
            raise ValueError("Mode cloud : cloud_serial et cloud_mac sont obligatoires")
        if not self.mqtt_host:
            raise ValueError("Aucun broker MQTT (ni option mqtt_host, ni service MQTT Supervisor)")
        self.device_id = re.sub(r"[^a-z0-9_]", "_", self.device_id.lower()) or "poele"
        self.refresh_interval = max(5.0, float(self.refresh_interval))
        self.unavailable_after = max(float(self.unavailable_after), self.refresh_interval * 3)
        self.ducted_fans = max(0, min(2, int(self.ducted_fans)))


def _coerce(value, target_type):
    if target_type is bool:
        return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "on")
    if target_type is int:
        return int(float(value))
    if target_type is float:
        return float(value)
    return "" if value is None else str(value)


def load() -> Config:
    raw: dict = {}
    if os.path.exists(OPTIONS_FILE):
        with open(OPTIONS_FILE, encoding="utf-8") as fh:
            raw = json.load(fh)

    # Broker fourni automatiquement par le Supervisor (voir run.sh) si mqtt_host est vide
    if not raw.get("mqtt_host"):
        for opt, env in (("mqtt_host", "SUPERVISOR_MQTT_HOST"), ("mqtt_port", "SUPERVISOR_MQTT_PORT"),
                         ("mqtt_user", "SUPERVISOR_MQTT_USER"), ("mqtt_password", "SUPERVISOR_MQTT_PASSWORD")):
            if os.environ.get(env):
                raw[opt] = os.environ[env]

    cfg = Config()
    types = {"str": str, "int": int, "float": float, "bool": bool}
    for f in fields(Config):
        key_env = f"MCZ_{f.name.upper()}"      # surcharge possible hors HA (docker/dev)
        val = os.environ.get(key_env, raw.get(f.name))
        if val is not None and val != "":
            setattr(cfg, f.name, _coerce(val, types[f.type] if isinstance(f.type, str) else f.type))
    cfg.validate()
    return cfg
