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
    assert P.build_commands("fan_ambient", "auto") == [(37, 6)]
    assert P.parse_legacy_commands("34,1;42,21") == [(34, 1), (42, 42)]
    assert P.write_param(34, 1) == "C|WriteParametri|34|1"
