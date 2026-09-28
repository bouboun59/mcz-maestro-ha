"""Transports vers le poêle : local (websocket) ou cloud MCZ (socket.io)."""
from __future__ import annotations

import logging
import threading
from typing import Callable

_LOG = logging.getLogger("maestro.transport")

FrameCallback = Callable[[str], None]
StatusCallback = Callable[[bool], None]


class Transport:
    """Interface commune."""

    name = "base"

    def __init__(self, on_frame: FrameCallback, on_status: StatusCallback) -> None:
        self._on_frame = on_frame
        self._on_status = on_status
        self._stop = threading.Event()
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def _set_connected(self, value: bool) -> None:
        if value != self._connected:
            self._connected = value
            _LOG.info("[%s] %s", self.name, "connecté" if value else "déconnecté")
            try:
                self._on_status(value)
            except Exception:  # noqa: BLE001
                _LOG.exception("Erreur callback statut")

    def start(self) -> None:
        threading.Thread(target=self._run, name=f"transport-{self.name}", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def send(self, message: str) -> bool:
        raise NotImplementedError

    def _run(self) -> None:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# LOCAL : websocket direct sur le module Maestro (AP 192.168.120.1:81 ou IP LAN)
# --------------------------------------------------------------------------- #
class LocalTransport(Transport):
    name = "local"

    def __init__(self, host: str, port: int, on_frame: FrameCallback, on_status: StatusCallback) -> None:
        super().__init__(on_frame, on_status)
        self._url = f"ws://{host}:{port}"
        self._ws = None
        self._lock = threading.Lock()

    def send(self, message: str) -> bool:
        with self._lock:
            ws = self._ws
            if ws is None or not self._connected:
                return False
            try:
                ws.send(message)
                _LOG.debug("[local] >> %s", message)
                return True
            except Exception as err:  # noqa: BLE001
                _LOG.warning("[local] envoi impossible (%s)", err)
                return False

    def _run(self) -> None:
        import websocket  # websocket-client

        backoff = 5
        while not self._stop.is_set():
            _LOG.info("[local] connexion à %s", self._url)

            def on_open(ws):
                nonlocal backoff
                backoff = 5
                self._set_connected(True)

            def on_message(ws, message):
                if isinstance(message, bytes):
                    message = message.decode(errors="ignore")
                _LOG.debug("[local] << %s", message[:120])
                self._on_frame(message)

            def on_error(ws, error):
                _LOG.warning("[local] erreur websocket : %s", error)

            def on_close(ws, code=None, msg=None):
                self._set_connected(False)

            app = websocket.WebSocketApp(
                self._url, on_open=on_open, on_message=on_message,
                on_error=on_error, on_close=on_close,
            )
            with self._lock:
                self._ws = app
            try:
                app.run_forever(ping_interval=10, ping_timeout=5, suppress_origin=True)
            except Exception:  # noqa: BLE001
                _LOG.exception("[local] run_forever a levé une exception")
            self._set_connected(False)
            with self._lock:
                self._ws = None
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, 60)


# --------------------------------------------------------------------------- #
# CLOUD : serveur socket.io MCZ (app Maestro « classique »)
# --------------------------------------------------------------------------- #
class CloudTransport(Transport):
    name = "cloud"

    def __init__(self, url: str, serial: str, mac: str,
                 on_frame: FrameCallback, on_status: StatusCallback) -> None:
        super().__init__(on_frame, on_status)
        self._url = url
        self._serial = serial.strip()
        self._mac = mac.strip().replace(":", "").replace("-", "")
        self._sio = None

    def _ident(self) -> dict:
        return {"serialNumber": self._serial, "macAddress": self._mac}

    def send(self, message: str) -> bool:
        sio = self._sio
        if sio is None or not self._connected:
            return False
        try:
            sio.emit("chiedo", {**self._ident(), "tipoChiamata": 1, "richiesta": message})
            _LOG.debug("[cloud] >> %s", message)
            return True
        except Exception as err:  # noqa: BLE001
            _LOG.warning("[cloud] envoi impossible (%s)", err)
            return False

    def _run(self) -> None:
        import socketio

        sio = socketio.Client(reconnection=True, reconnection_delay=5,
                              reconnection_delay_max=60, logger=False, engineio_logger=False)
        self._sio = sio

        @sio.event
        def connect():
            _LOG.info("[cloud] socket.io connecté (sid=%s), join %s", sio.sid, self._serial)
            sio.emit("join", {**self._ident(), "type": "Android-App"})
            sio.emit("chiedo", {**self._ident(), "tipoChiamata": 0, "richiesta": "RecuperoParametri"})
            self._set_connected(True)
            sio.emit("chiedo", {**self._ident(), "tipoChiamata": 1, "richiesta": "C|RecuperoInfo"})

        @sio.event
        def disconnect(*_args):
            self._set_connected(False)

        @sio.on("rispondo")
        def rispondo(data):
            try:
                frame = data.get("stringaRicevuta", "") if isinstance(data, dict) else str(data)
            except Exception:  # noqa: BLE001
                return
            _LOG.debug("[cloud] << %s", str(frame)[:120])
            self._on_frame(frame)

        backoff = 5
        while not self._stop.is_set():
            try:
                _LOG.info("[cloud] connexion à %s", self._url)
                sio.connect(self._url, wait_timeout=20)
                backoff = 5
                sio.wait()  # bloque tant que le client (avec reconnexion auto) est actif
            except Exception as err:  # noqa: BLE001
                _LOG.warning("[cloud] connexion impossible : %s", err)
            self._set_connected(False)
            try:
                sio.disconnect()
            except Exception:  # noqa: BLE001
                pass
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, 300)
