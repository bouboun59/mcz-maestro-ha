"""Point d'entrée : python3 -m mcz_maestro"""
import logging
import signal
import sys

from . import config
from .gateway import Gateway


def main() -> int:
    try:
        cfg = config.load()
    except Exception as err:  # noqa: BLE001
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("maestro").error("Configuration invalide : %s", err)
        return 1

    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    for noisy in ("engineio", "socketio", "websocket", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING if cfg.log_level != "debug" else logging.INFO)

    gw = Gateway(cfg)

    def _stop(*_):
        gw.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    gw.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
