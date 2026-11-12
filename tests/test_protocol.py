import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "mcz_maestro/rootfs/app"))
from mcz_maestro import protocol as P  # noqa: E402


def _frame(**over):
    v = [0] * 61
    v[1], v[6], v[26], v[29], v[37] = 11, 41, 42, 13, 7200
    for k, val in over.items():
        v[int(k[1:])] = val
    return "01|" + "|".join(format(x, "X") for x in v[1:])


def test_parse_basic():
    m, legacy = P.parse_info_frame(_frame())
    assert m["stove_state"] == "Puissance 1"
    assert m["power"] == "ON" and m["hvac_action"] == "heating"
    assert m["ambient_temperature"] == 20.5 and m["setpoint"] == 21.0
    assert m["power_level"] == 3
    assert m["operating_hours_total"] == 2.0
    assert legacy["Etat du poele"] == "Puissance 1"


def test_alarm():
    m, _ = P.parse_info_frame(_frame(i1=51))
    assert m["alarm"] == "ON" and m["power"] == "OFF"


def test_commands():
    assert P.build_commands("setpoint", "22.5") == [(40, 1), (42, 45)]
    assert P.build_commands("setpoint", "22.5", auto_regulation=False) == [(42, 45)]
    assert P.build_commands("power", "OFF") == [(34, 40)]
    assert P.build_commands("power_level", "4", auto_regulation=False) == [(40, 0), (36, 4)]
    assert P.build_commands("fan_ambient", "auto") == [(37, 6)]
    assert P.parse_legacy_commands("34,1;42,21") == [(34, 1), (42, 42)]
    assert P.write_param(34, 1) == "C|WriteParametri|34|1"


def test_fields_from_apk():
    # 48 = unité °C/°F, 49 = effets sonores, 50 = sleep en pas de 10 min
    m, _ = P.parse_info_frame(_frame(i48=0, i49=1, i50=6, i46=40, i52=41, i53=255, i18=13))
    assert m["temperature_unit"] == 0 and m["sound_effects_sw"] == "ON"
    assert m["sleep_minutes"] == 60 and m["sleep_sw"] == "ON"
    assert m["active_temperature"] == 20.0
    assert m["wifi_probe1"] == 20.5 and "wifi_probe2" not in m
    assert m["profile_mode"] == "comfort" and m["adaptive_sw"] == "ON"
    m, _ = P.parse_info_frame(_frame(i49=0, i50=0, i18=4))
    assert m["sound_effects_sw"] == "OFF" and m["sleep_sw"] == "OFF"
    assert m["profile_mode"] == "power" and m["adaptive_sw"] == "OFF"


def test_firmware():
    v = ["0"] * 60
    v[0], v[29] = "B", "0109"
    m, _ = P.parse_info_frame("01|" + "|".join(v))
    assert m["firmware"] == "1.9"


def test_new_commands():
    assert P.build_commands("profile", "dynamic") == [(149, 1)]
    assert P.build_commands("profile", "power", state={"profile": 11}) == [(149, 14)]
    assert P.build_commands("adaptive", "ON", state={"profile": 3}) == [(149, 13)]
    assert P.build_commands("adaptive", "OFF", state={"profile": 13}) == [(149, 3)]
    assert P.build_commands("sleep", "90") == [(57, 9)]
    assert P.build_commands("sleep", "0") == [(57, 0)]
    assert P.build_commands("reset_active", "1") == [(2, 255)]
    assert P.build_commands("chrono_t2", "19") == [(1109, 19)]
    for bad in (("sleep", "600"), ("chrono_t1", "40"), ("profile", "turbo")):
        try:
            P.build_commands(*bad)
        except (ValueError, KeyError):
            pass
        else:
            raise AssertionError(bad)


def test_chrono():
    slots = [0] * 48
    slots[12:17] = [2] * 5          # 06:00-08:30 T2
    slots[34:44] = [3] * 10         # 17:00-22:00 T3
    day = P.encode_chrono_day(slots)
    assert len(day) == 24 and P.decode_chrono_day(day) == slots
    frame = "04|" + "|".join([day] * 7) + "|10|13|15"
    c = P.parse_chrono_frame(frame)
    assert c["chrono_schedule"]["lundi"] == "06:00-08:30 T2, 17:00-22:00 T3"
    assert (c["chrono_t1"], c["chrono_t2"], c["chrono_t3"]) == (16, 19, 21)
    assert P.chrono_day_command("mardi|" + day) == f"C|ScriviGiornoChrono|1|{day}"


def test_alarms_and_clock():
    a = P.parse_alarms_frame("0A|33|5f5e1000|35|5f5e2000|00|ffffffff")
    # la plus récente d'abord (0x35 = A04, horodatée après 0x33 = A02)
    assert a["last_alarm"].startswith("Erreur A04") and len(a["alarm_history"]) == 2
    assert a["alarm_history"][1]["code"] == 0x33
    import time as _t
    assert P.clock_command(_t.strptime("2026-11-12 22:05", "%Y-%m-%d %H:%M")) == "C|SalvaDataOra|121120262205"


def test_recipes():
    assert P.parse_extra_frame("03|03|02|ff|3c|02") == {"air_recipe": "+1", "pellet_recipe": "-1"}
    assert P.build_commands("air_recipe", "+1") == [(P.BANK_OFFSET + 459, 3)]
    assert P.build_commands("pellet_recipe", "2") == [(P.BANK_OFFSET + 460, 5)]
    assert P.write_param(P.BANK_OFFSET + 459, 3) == "C|WriteBancaDati|459|1|03"
    assert P.write_param(P.BANK_OFFSET + 460, 0) == "C|WriteBancaDati|460|1|00"
