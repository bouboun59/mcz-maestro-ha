"""Protocole MCZ Maestro (classique) : décodage de la trame RecuperoInfo et encodage des commandes.

Le même protocole texte est utilisé en local (websocket ws://<poele>:81) et en cloud
(socket.io app.mcz.it:9000, champ 'richiesta' / 'stringaRicevuta').
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

INFO_REQUEST = "C|RecuperoInfo"
EXTRA_REQUEST = "C|RecuperoParametriExtra|11"
MSG_TYPE_INFO = "01"
MSG_TYPE_EXTRA = "03"

# --------------------------------------------------------------------------- #
# États du poêle : code -> (libellé FR, allumé ?)
# --------------------------------------------------------------------------- #
STOVE_STATES: dict[int, tuple[str, bool]] = {
    0: ("Eteint", False),
    1: ("Controle du poele froid / chaud", True),
    2: ("Clean Froid", True),
    3: ("Load Froid", True),
    4: ("Start 1 Froid", True),
    5: ("Start 2 Froid", True),
    6: ("Clean Chaud", True),
    7: ("Load Chaud", True),
    8: ("Start 1 chaud", True),
    9: ("Start 2 chaud", True),
    10: ("Stabilisation", True),
    11: ("Puissance 1", True),
    12: ("Puissance 2", True),
    13: ("Puissance 3", True),
    14: ("Puissance 4", True),
    15: ("Puissance 5", True),
    30: ("Mode diagnostique", False),
    31: ("Marche", True),
    40: ("Extinction", False),
    41: ("Refroidissement en cours", False),
    42: ("Nettoyage basse p.", False),
    43: ("Nettoyage haute p.", False),
    44: ("Debloquage vis sans fin", False),
    45: ("AUTO ECO", True),
    46: ("Standby", True),
    48: ("Diagnostique", False),
    49: ("CHARG. VIS SANS FIN", False),
    50: ("Erreur A01 - Allumage rate", False),
    51: ("Erreur A02 - Pas de flamme", False),
    52: ("Erreur A03 - Surchauffe du reservoir", False),
    53: ("Erreur A04 - Temperature des fumees trop haute", False),
    54: ("Erreur A05 - Obstruction conduit - Vent", False),
    55: ("Erreur A06 - Mauvais tirage", False),
    56: ("Erreur A09 - Defaillance sonde de fumees", False),
    57: ("Erreur A11 - Defaillance motoreducteur", False),
    58: ("Erreur A13 - Temperature carte mere trop haute", False),
    59: ("Erreur A14 - Defaut Active", False),
    60: ("Erreur A18 - Temperature d'eau trop haute", False),
    61: ("Erreur A19 - Defaut sonde temperature eau", False),
    62: ("Erreur A20 - Defaut sonde auxiliaire", False),
    63: ("Erreur A21 - Alarme pressostat", False),
    64: ("Erreur A22 - Defaut sonde ambiante", False),
    65: ("Erreur A23 - Defaut fermeture brasero", False),
    66: ("Erreur A12 - Panne controleur motoreducteur", False),
    67: ("Erreur A17 - Bourrage vis sans fin", False),
    69: ("Attente Alarmes securite", False),
}

FAN_LEVELS = {0: "Desactive", 1: "Niveau 1", 2: "Niveau 2", 3: "Niveau 3",
              4: "Niveau 4", 5: "Niveau 5", 6: "Automatique"}
ON_OFF = {0: "Off", 1: "On"}
PROFILES = {0: "Manuel", 1: "Dynamic", 2: "Overnight", 3: "Comfort",
            4: "Power 110%", 10: "Mode Adaptatif"}
PELLET = {0: "Sonde pas active", 10: "Niveau suffisant", 11: "Niveau presque vide"}
BRAZIER = {0: "OK", 100: "Fermeture brazero", 101: "Ouverture brazero"}
REGULATION = {0: "Manuelle", 1: "Dynamique"}
SEASON = {0: "Hiver", 1: "Ete"}
POWER_ACTIVE = {11: "Puissance 1", 12: "Puissance 2", 13: "Puissance 3",
                14: "Puissance 4", 15: "Puissance 5"}


@dataclass(frozen=True)
class Field:
    index: int          # position dans la trame "01|..."
    key: str            # clé JSON « moderne » (topic <base>/state)
    legacy: str         # libellé historique (JSON Maestro/State du script cloud)
    kind: str = "int"   # int | temp | seconds | map
    mapping: dict | None = None


FIELDS: list[Field] = [
    Field(1, "stove_state_code", "Etat du poele", "map", {k: v[0] for k, v in STOVE_STATES.items()}),
    Field(2, "fan_ambient", "Etat du ventilateur ambiance", "map", FAN_LEVELS),
    Field(3, "fan_ducted1", "Etat du ventilateur canalise 1", "map", FAN_LEVELS),
    Field(4, "fan_ducted2", "Etat du ventilateur canalise 2", "map", FAN_LEVELS),
    Field(5, "fumes_temperature", "Temperature des fumees"),
    Field(6, "ambient_temperature", "Temperature ambiante", "temp"),
    Field(7, "puffer_temperature", "Puffer Temperature", "temp"),
    Field(8, "boiler_temperature", "Temperature chaudiere", "temp"),
    Field(9, "ntc3_temperature", "Temperature NTC3", "temp"),
    Field(10, "candle", "Etat de la bougie", "map", ON_OFF),
    Field(11, "active_set", "ACTIVE - Set"),
    Field(12, "fumes_fan_rpm", "RPM - Ventilateur fumees"),
    Field(13, "auger_rpm_set", "RPM - Vis sans fin - SET"),
    Field(14, "auger_rpm_live", "RPM - Vis sans fin - LIVE"),
    Field(17, "brazier", "Brazero", "map", BRAZIER),
    Field(18, "profile", "Profil", "map", PROFILES),
    Field(20, "active_mode", "Etat du mode Active", "map", ON_OFF),
    Field(21, "active_live", "ACTIVE - Live"),
    Field(22, "regulation_mode", "Mode de regulation", "map", REGULATION),
    Field(23, "eco_mode", "Mode ECO", "map", ON_OFF),
    Field(24, "silent_mode", "Silence", "map", ON_OFF),
    Field(25, "chronostat", "Mode Chronotermostato", "map", ON_OFF),
    Field(26, "setpoint", "TEMP - Consigne", "temp"),
    Field(27, "boiler_setpoint", "TEMP - Boiler", "temp"),
    Field(28, "motherboard_temperature", "TEMP - Carte mere", "temp"),
    Field(29, "power_level", "Puissance Active", "map", POWER_ACTIVE),
    Field(32, "stove_hour", "Heure du poele (0-23)"),
    Field(33, "stove_minute", "Minutes du poele (0-29)"),
    Field(34, "stove_day", "Jour du poele (1-31)"),
    Field(35, "stove_month", "Mois du poele (1-12)"),
    Field(36, "stove_year", "Annee du poele"),
    Field(37, "operating_seconds_total", "Heures de fonctionnement total (s)", "seconds"),
    Field(38, "operating_seconds_p1", "Heures de fonctionnement en puissance 1 (s)", "seconds"),
    Field(39, "operating_seconds_p2", "Heures de fonctionnement en puissance 2 (s)", "seconds"),
    Field(40, "operating_seconds_p3", "Heures de fonctionnement en puissance 3 (s)", "seconds"),
    Field(41, "operating_seconds_p4", "Heures de fonctionnement en puissance 4 (s)", "seconds"),
    Field(42, "operating_seconds_p5", "Heures de fonctionnement en puissance 5 (s)", "seconds"),
    Field(43, "hours_to_service", "Heures avant entretien"),
    Field(44, "minutes_to_switch_off", "Minutes avant extinction"),
    Field(45, "ignitions", "Nombre d'allumages"),
    Field(47, "pellet_sensor", "Sonde Pellets", "map", PELLET),
    Field(48, "sound_effects", "Effet sonore", "map", ON_OFF),
    Field(49, "sound_effects_state", "Etat effets sonores", "map", ON_OFF),
    Field(50, "sleep", "Sleep", "map", ON_OFF),
    Field(51, "season", "Mode", "map", SEASON),
    Field(52, "wifi_probe1", "Sonde wifi temperature 1"),
    Field(53, "wifi_probe2", "Sonde wifi temperature 2"),
    Field(54, "wifi_probe3", "Sonde wifi temperature 3"),
    Field(55, "unknown_55", "Inconnu"),
    Field(56, "set_puffer", "Set Puffer"),
    Field(57, "set_boiler", "Set Boiler"),
    Field(58, "set_health", "Set Health"),
    Field(59, "return_temperature", "Temperature retour", "temp"),
    Field(60, "antifreeze", "Antigel", "map", ON_OFF),
]

# Indices divisés par 2 dans le JSON historique (compatibilité stricte avec l'ancien script cloud)
_LEGACY_HALF = {6, 26, 28}


def _dhms(seconds: int) -> str:
    qm, s = divmod(seconds, 60)
    qh, m = divmod(qm, 60)
    d, h = divmod(qh, 24)
    return f"{d}:{h}:{m}:{s}"


def is_info_frame(message: str) -> bool:
    return isinstance(message, str) and message.split("|", 1)[0] == MSG_TYPE_INFO


# --------------------------------------------------------------------------- #
# Recettes de combustion (« Ricetta Aria » / « Ricetta Pellet » de l'app MCZ)
# Lecture : C|RecuperoParametriExtra|11 -> 03|<air>|<pellets>|<entrée ambiance>|...
# Écriture : C|WriteBancaDati|<cellule>|1|<valeur hex 2 chiffres>
# --------------------------------------------------------------------------- #
AIR_RECIPE_OPTIONS = ["-2", "-1", "0", "+1", "+2"]                  # valeurs 0..4
PELLET_RECIPE_OPTIONS = ["-3", "-2", "-1", "0", "+1", "+2", "+3"]   # valeurs 0..6
BANK_AIR_RECIPE = 459
BANK_PELLET_RECIPE = 460
BANK_OFFSET = 100000   # identifiant interne : >= BANK_OFFSET = cellule de la banque de données


def is_extra_frame(message: str) -> bool:
    return isinstance(message, str) and message.split("|", 1)[0] == MSG_TYPE_EXTRA


def parse_extra_frame(message: str) -> dict[str, Any]:
    raw = message.strip().split("|")
    out: dict[str, Any] = {}
    for idx, key, opts in ((1, "air_recipe", AIR_RECIPE_OPTIONS), (2, "pellet_recipe", PELLET_RECIPE_OPTIONS)):
        if idx < len(raw):
            try:
                v = int(raw[idx], 16)
            except ValueError:
                continue
            if 0 <= v < len(opts):
                out[key] = opts[v]
    return out


def _recipe(cell: int, opts: list[str]):
    def build(payload: str) -> list[tuple[int, int]]:
        p = str(payload).strip()
        if p and p[0].isdigit() and p != "0":
            p = "+" + p
        if p not in opts:
            raise ValueError(f"valeur attendue parmi {opts}")
        return [(BANK_OFFSET + cell, opts.index(p))]
    return build


def parse_info_frame(message: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Décode une trame « 01|... ».

    Retourne (état moderne, état historique FR).
    """
    raw = message.strip().split("|")
    modern: dict[str, Any] = {}
    legacy: dict[str, Any] = {}

    for f in FIELDS:
        if f.index >= len(raw):
            continue
        try:
            val = int(raw[f.index], 16)
        except ValueError:
            continue

        # ---- valeur moderne (numérique, exploitable directement par HA)
        if f.kind == "temp":
            modern[f.key] = val / 2
        elif f.kind == "seconds":
            modern[f.key] = val
        else:
            modern[f.key] = val

        # ---- valeur historique (identique à l'ancien script cloud)
        if f.mapping is not None:
            legacy[f.legacy] = f.mapping.get(val, f"Code inconnu : {val}")
        elif f.index in _LEGACY_HALF:
            legacy[f.legacy] = val / 2
        elif 37 <= f.index <= 42:
            legacy[f.legacy] = _dhms(val)
        else:
            legacy[f.legacy] = val

    # ---- champs dérivés
    code = modern.get("stove_state_code")
    if code is not None:
        label, running = STOVE_STATES.get(code, (f"Code inconnu : {code}", False))
        modern["stove_state"] = label
        modern["power"] = "ON" if running else "OFF"
        modern["alarm"] = "ON" if 50 <= code <= 69 else "OFF"
        modern["diagnostics"] = "ON" if code in (30, 48) else "OFF"
        if code == 0 or 40 <= code <= 44 or code >= 48:
            modern["hvac_action"] = "off"
        elif code in (45, 46):
            modern["hvac_action"] = "idle"
        else:
            modern["hvac_action"] = "heating"
        modern["hvac_mode"] = "heat" if running else "off"

    lvl = modern.get("power_level")
    if lvl is not None:
        modern["power_level"] = lvl - 10 if lvl >= 11 else lvl

    if "operating_seconds_total" in modern:
        modern["operating_hours_total"] = round(modern["operating_seconds_total"] / 3600, 1)

    if "pellet_sensor" in modern:
        modern["pellet_low"] = "ON" if modern["pellet_sensor"] == 11 else "OFF"

    for key in ("fan_ambient", "fan_ducted1", "fan_ducted2"):
        if key in modern:
            modern[f"{key}_mode"] = FAN_OPTIONS_BY_VALUE.get(modern[key], str(modern[key]))

    if "regulation_mode" in modern:
        modern["regulation"] = "auto" if modern["regulation_mode"] == 1 else "manual"

    for key in ("eco_mode", "silent_mode", "active_mode", "chronostat", "sound_effects",
                "sleep", "antifreeze", "candle"):
        if key in modern:
            modern[f"{key}_sw"] = "ON" if modern[key] == 1 else "OFF"
    if "season" in modern:
        modern["summer_sw"] = "ON" if modern["season"] == 1 else "OFF"

    if all(k in modern for k in ("stove_year", "stove_month", "stove_day", "stove_hour", "stove_minute")):
        modern["stove_datetime"] = (
            f"{modern['stove_year']:04d}-{modern['stove_month']:02d}-{modern['stove_day']:02d} "
            f"{modern['stove_hour']:02d}:{modern['stove_minute']:02d}"
        )

    return modern, legacy


# --------------------------------------------------------------------------- #
# Commandes
# --------------------------------------------------------------------------- #
FAN_OPTIONS = ["off", "1", "2", "3", "4", "5", "auto"]
FAN_OPTIONS_BY_VALUE = {i: v for i, v in enumerate(FAN_OPTIONS)}

PARAM_POWER = 34
PARAM_ACTIVE = 35
PARAM_POWER_LEVEL = 36
PARAM_FAN_AMBIENT = 37
PARAM_FAN_DUCTED1 = 38
PARAM_FAN_DUCTED2 = 39
PARAM_REGULATION = 40
PARAM_ECO = 41
PARAM_SETPOINT = 42
PARAM_SILENT = 45
PARAM_SOUND = 50
PARAM_BOILER_SETPOINT = 51
PARAM_SLEEP = 57
PARAM_SUMMER = 58
PARAM_PELLET_SENSOR = 148
PARAM_ADAPTIVE = 149
PARAM_ANTIFREEZE = 154
PARAM_CHRONO = 1111
PARAM_RESET_ALARM = 1


def write_param(param_id: int, value: int) -> str:
    if param_id >= BANK_OFFSET:
        return f"C|WriteBancaDati|{int(param_id) - BANK_OFFSET}|1|{int(value):02X}"
    return f"C|WriteParametri|{int(param_id)}|{int(value)}"


def _truthy(payload: str) -> bool:
    return str(payload).strip().lower() in ("1", "on", "true", "yes", "heat")


def _fan(payload: str) -> int:
    p = str(payload).strip().lower()
    if p in FAN_OPTIONS:
        return FAN_OPTIONS.index(p)
    v = int(float(p))
    if not 0 <= v <= 6:
        raise ValueError("ventilation hors plage 0-6")
    return v


def _temp(payload: str) -> int:
    return int(round(float(payload) * 2))


def _level(payload: str) -> int:
    v = int(float(payload))
    if not 1 <= v <= 5:
        raise ValueError("puissance hors plage 1-5")
    return v


def _onoff(param: int):
    return lambda p: [(param, 1 if _truthy(p) else 0)]


def build_commands(name: str, payload: str, auto_regulation: bool = True) -> list[tuple[int, int]]:
    """Traduit une commande MQTT « nommée » en liste de (paramètre, valeur)."""
    name = name.strip().lower()
    table = {
        "power": lambda p: [(PARAM_POWER, 1 if _truthy(p) else 40)],
        "hvac_mode": lambda p: [(PARAM_POWER, 1 if _truthy(p) else 40)],
        "setpoint": lambda p: ([(PARAM_REGULATION, 1)] if auto_regulation else []) + [(PARAM_SETPOINT, _temp(p))],
        "power_level": lambda p: ([(PARAM_REGULATION, 0)] if auto_regulation else []) + [(PARAM_POWER_LEVEL, _level(p))],
        "regulation": lambda p: [(PARAM_REGULATION, 1 if str(p).strip().lower() in ("auto", "1", "on") else 0)],
        "fan_ambient": lambda p: [(PARAM_FAN_AMBIENT, _fan(p))],
        "fan_ducted1": lambda p: [(PARAM_FAN_DUCTED1, _fan(p))],
        "fan_ducted2": lambda p: [(PARAM_FAN_DUCTED2, _fan(p))],
        "eco": _onoff(PARAM_ECO),
        "silent": _onoff(PARAM_SILENT),
        "active": _onoff(PARAM_ACTIVE),
        "sound": _onoff(PARAM_SOUND),
        "sleep": _onoff(PARAM_SLEEP),
        "summer": _onoff(PARAM_SUMMER),
        "chrono": _onoff(PARAM_CHRONO),
        "antifreeze": _onoff(PARAM_ANTIFREEZE),
        "adaptive": _onoff(PARAM_ADAPTIVE),
        "pellet_sensor": _onoff(PARAM_PELLET_SENSOR),
        "boiler_setpoint": lambda p: [(PARAM_BOILER_SETPOINT, _temp(p))],
        "reset_alarm": lambda p: [(PARAM_RESET_ALARM, 255)],
        "air_recipe": _recipe(BANK_AIR_RECIPE, AIR_RECIPE_OPTIONS),
        "pellet_recipe": _recipe(BANK_PELLET_RECIPE, PELLET_RECIPE_OPTIONS),
    }
    if name not in table:
        raise KeyError(name)
    return table[name](payload)


def parse_legacy_commands(payload: str) -> list[tuple[int, int]]:
    """Format historique « id,valeur » ou plusieurs commandes « id,valeur;id,valeur ».

    Comme l'ancien script : la consigne (42) est donnée en °C et multipliée par 2.
    """
    out: list[tuple[int, int]] = []
    for chunk in str(payload).replace("\n", ";").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        pid, val = (x.strip() for x in chunk.split(",", 1))
        pid_i = int(pid)
        val_i = _temp(val) if pid_i == PARAM_SETPOINT else int(float(val))
        out.append((pid_i, val_i))
    return out
