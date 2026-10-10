"""Physical weight measurement.

Backends
--------
``serial``
    An HX711 load cell connected to an Arduino/ESP32 streaming readings over
    USB serial (see ``firmware/scale_controller``). Readings from this backend
    are marked ``source="real"``.
``mock``
    A deterministic simulated sensor for development, demos and automated
    tests. Readings are always marked ``source="simulated"`` and must never be
    presented as hardware measurements.
``disabled``
    Sensor explicitly switched off.

The module never assumes a sensor is calibrated: ``calibrated`` stays False
until :meth:`WeightSensor.calibrate` succeeds with a known reference weight
(or a factor is supplied through configuration).
"""

from __future__ import annotations

import math
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.core.config import Settings


class SensorError(RuntimeError):
    """Base class for sensor failures (connection, timeout, bad data)."""

    kind = "sensor_error"


class SensorConnectionError(SensorError):
    kind = "connection_error"


class SensorTimeoutError(SensorError):
    kind = "timeout"


class SensorDataError(SensorError):
    kind = "invalid_data"


class SensorNotCalibratedError(SensorError):
    kind = "not_calibrated"


@dataclass
class Reading:
    """One weight observation."""

    grams: float | None = None
    raw: float | None = None
    stable: bool = False
    source: str = "none"  # real | simulated | none
    timestamp: float = field(default_factory=time.time)
    message: str = ""

    @property
    def kg(self) -> float | None:
        return None if self.grams is None else self.grams / 1000.0

    def format(self) -> str:
        if self.grams is None:
            return "n/a"
        if abs(self.grams) >= 1000:
            return f"{self.grams / 1000:.3f} kg"
        return f"{self.grams:.1f} g"


def convert_units(grams: float | None, target: str) -> float | None:
    """Convert grams to ``g`` or ``kg``; returns None for None input."""
    if grams is None:
        return None
    target = target.lower()
    if target in ("g", "gram", "grams"):
        return grams
    if target in ("kg", "kilogram", "kilograms"):
        return grams / 1000.0
    raise ValueError(f"Unsupported unit: {target!r} (use 'g' or 'kg')")


class WeightSensor:
    """Shared behaviour: stability window, tare/calibration bookkeeping."""

    backend = "disabled"
    simulated = False

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._connected = False
        self._calibrated = False
        self._offset_raw = 0.0
        self._factor = 1.0  # grams per raw-count
        self._history: deque[tuple[float, float]] = deque(maxlen=64)  # (t, grams)
        self._last_raw: float | None = None
        self._last_grams: float | None = None
        self._last_message = ""
        self._calibration_meta: dict = {}

    # ------------------------------------------------------------------ status
    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def calibrated(self) -> bool:
        return self._calibrated

    @property
    def factor(self) -> float:
        return self._factor

    @property
    def offset_raw(self) -> float:
        return self._offset_raw

    def status(self) -> dict:
        stable = self._is_stable()
        return {
            "backend": self.backend,
            "connected": self._connected,
            "calibrated": self._calibrated,
            "simulated": self.simulated,
            "port": getattr(self, "port", None),
            "last_reading_g": self._last_grams,
            "stable": stable,
            "message": self._last_message,
        }

    # ------------------------------------------------------------------ lifecycle
    def connect(self) -> bool:
        raise NotImplementedError

    def disconnect(self) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------ measurement
    def read(self, timeout: float | None = None) -> Reading:
        """Return one reading. Raises SensorError subclasses on failure."""
        raise NotImplementedError

    def tare(self, samples: int = 10) -> Reading:
        """Zero the scale at the current load (empty platform)."""
        raise NotImplementedError

    def calibrate(self, reference_weight_g: float, samples: int = 20) -> float:
        """Derive the calibration factor from a known reference weight."""
        raise NotImplementedError

    # ------------------------------------------------------------------ stability
    def _push(self, t: float, grams: float) -> None:
        self._history.append((t, grams))

    def _is_stable(self) -> bool:
        window = self.settings.sensor_stability_window_s
        now = time.time()
        recent = [g for t, g in self._history if now - t <= window]
        if len(recent) < self.settings.sensor_stability_samples:
            return False
        return (max(recent) - min(recent)) <= self.settings.sensor_stability_delta_g

    def wait_for_stable(self, timeout: float | None = None, interval: float = 0.15) -> Reading:
        """Poll until readings settle within the configured tolerance."""
        deadline = time.time() + (
            timeout if timeout is not None else self.settings.sensor_timeout_s
        )
        last: Reading | None = None
        while time.time() < deadline:
            try:
                last = self.read(timeout=max(0.05, deadline - time.time()))
            except SensorError as exc:
                raise exc
            if last.grams is not None and self._is_stable():
                last.stable = True
                return last
            time.sleep(interval)
        if last is None:
            raise SensorTimeoutError("No weight reading before timeout.")
        last.stable = False
        last.message = last.message or "Reading has not stabilised yet."
        return last

    def _reading(self, grams: float | None, raw: float | None, message: str = "") -> Reading:
        self._last_grams = grams
        self._last_raw = raw
        self._last_message = message
        if grams is not None:
            # Push the fresh sample BEFORE evaluating stability so the current
            # reading participates in the window (a jump must invalidate it).
            self._push(time.time(), grams)
        reading = Reading(
            grams=grams,
            raw=raw,
            stable=grams is not None and self._is_stable(),
            source="simulated" if self.simulated else "real",
            message=message,
        )
        return reading


# --------------------------------------------------------------------------- mock
class MockWeightSensor(WeightSensor):
    """Deterministic simulated load cell.

    Simulated readings are *always* flagged with ``source="simulated"`` so the
    UI can label them; they are never passed off as hardware measurements.
    """

    backend = "mock"
    simulated = True

    def __init__(self, settings: Settings, seed: int = 42) -> None:
        super().__init__(settings)
        self.port = None
        self._target_g = 0.0
        self._rng = random.Random(seed)
        self._noise_g = 0.4
        self._calibrated = True  # simulation needs no physical calibration
        self._last_message = "Simulated sensor (mock). Readings are NOT real measurements."

    def set_weight(self, grams: float | None, noise_g: float = 0.4) -> None:
        """Set the simulated platform load (None = no object / unstable drop)."""
        with self._lock:
            self._target_g = 0.0 if grams is None else float(grams)
            self._noise_g = noise_g

    @property
    def target_g(self) -> float:
        return self._target_g

    def connect(self) -> bool:
        self._connected = True
        self._last_message = "Simulated sensor (mock). Readings are NOT real measurements."
        return True

    def disconnect(self) -> None:
        self._connected = False

    def read(self, timeout: float | None = None) -> Reading:
        if not self._connected:
            self.connect()
        with self._lock:
            noise = self._rng.gauss(0.0, self._noise_g)
            grams = self._target_g + noise
            if abs(grams) < 0.05:
                grams = 0.0
            raw = grams / self._factor + self._offset_raw
        return self._reading(
            round(grams, 2),
            round(raw, 2),
            "Simulated reading — not a real sensor measurement.",
        )

    def tare(self, samples: int = 10) -> Reading:
        if not self._connected:
            self.connect()
        with self._lock:
            # Taring an empty simulated platform zeroes the current load.
            observed = [self._target_g + self._rng.gauss(0.0, self._noise_g) for _ in range(samples)]
            self._offset_raw = mean(observed) / self._factor + self._offset_raw
            if abs(self._target_g) < 1.0:
                self._target_g = 0.0
            self._history.clear()
        self._last_message = "Mock tare complete (simulated)."
        return self._reading(0.0, self._offset_raw, self._last_message)

    def calibrate(self, reference_weight_g: float, samples: int = 20) -> float:
        if reference_weight_g <= 0:
            raise ValueError("Reference weight must be > 0 g")
        if not self._connected:
            self.connect()
        with self._lock:
            previous_target = self._target_g
            # Simulate placing the reference weight on the platform.
            self._target_g = float(reference_weight_g)
            observed = [
                self._target_g + self._rng.gauss(0.0, self._noise_g) for _ in range(max(samples, 5))
            ]
            raw_mean = mean(observed)
            self._target_g = previous_target
            numerator = raw_mean - self._offset_raw
            if abs(numerator) < 1e-9:
                raise SensorDataError("Cannot calibrate: raw reading equals tare offset.")
            self._factor = float(reference_weight_g) / numerator
            self._calibrated = True
            self._calibration_meta = {
                "reference_weight_g": float(reference_weight_g),
                "raw_reading_at_calibration": raw_mean,
                "factor": self._factor,
                "simulated": True,
            }
        self._last_message = "Mock calibration complete (simulated)."
        return self._factor


# --------------------------------------------------------------------------- serial
class SerialHX711Sensor(WeightSensor):
    """HX711 load cell via an Arduino/ESP32 USB serial bridge.

    Line protocol (see ``firmware/scale_controller/README.md``):

    * device -> host: ``RAW,<counts>`` (streamed), ``OK,<msg>``, ``ERR,<msg>``
    * host -> device: ``TARE``, ``CAL,<factor>``, ``PING``
    """

    backend = "serial"
    simulated = False

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.port = settings.sensor_port or None
        self.baudrate = settings.sensor_baudrate
        self._serial = None
        self._last_message = "Serial sensor not connected."

    # ------------------------------------------------------------------ lifecycle
    def connect(self) -> bool:
        if self._connected and self._serial is not None:
            return True
        if not self.port:
            raise SensorConnectionError(
                "No serial port configured. Set SENSOR_PORT (e.g. COM3) in .env."
            )
        try:
            import serial  # pyserial
        except ImportError as exc:  # pragma: no cover
            raise SensorConnectionError("pyserial is not installed.") from exc
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.4,
                write_timeout=0.4,
            )
        except Exception as exc:  # noqa: BLE001
            self._serial = None
            self._connected = False
            raise SensorConnectionError(f"Could not open {self.port}: {exc}") from exc
        time.sleep(0.4)  # allow Arduino auto-reset to finish
        self._connected = True
        self._last_message = f"Connected to {self.port} @ {self.baudrate} baud."
        return True

    def disconnect(self) -> None:
        with self._lock:
            if self._serial is not None:
                try:
                    self._serial.close()
                except Exception:  # pragma: no cover
                    pass
            self._serial = None
            self._connected = False
            self._last_message = "Serial sensor disconnected."

    def _send(self, command: str) -> None:
        if self._serial is None:
            raise SensorConnectionError("Serial port is not open.")
        try:
            self._serial.write((command + "\n").encode("ascii", errors="ignore"))
        except Exception as exc:  # noqa: BLE001
            raise SensorConnectionError(f"Serial write failed: {exc}") from exc

    def _readline(self, deadline: float) -> str:
        if self._serial is None:
            raise SensorConnectionError("Serial port is not open.")
        while time.time() < deadline:
            try:
                raw = self._serial.readline()
            except Exception as exc:  # noqa: BLE001
                raise SensorConnectionError(f"Serial read failed: {exc}") from exc
            if not raw:
                continue
            line = raw.decode("ascii", errors="ignore").strip()
            if line:
                return line
        raise SensorTimeoutError(
            f"No data from {self.port} within timeout. Check wiring, baud rate, "
            "and that no other program is using the port."
        )

    def _next_raw(self, deadline: float) -> float:
        """Read lines until a RAW value arrives (handles OK/ERR noise)."""
        while True:
            line = self._readline(deadline)
            if line.startswith("RAW,"):
                payload = line[4:].strip()
                try:
                    return float(payload)
                except ValueError as exc:
                    raise SensorDataError(f"Malformed RAW value: {line!r}") from exc
            if line.startswith("ERR,"):
                raise SensorDataError(line[4:].strip() or "Device reported an error.")
            # OK / banner lines are ignored

    # ------------------------------------------------------------------ measurement
    def read(self, timeout: float | None = None) -> Reading:
        if not self._connected:
            self.connect()
        timeout = timeout if timeout is not None else self.settings.sensor_timeout_s
        deadline = time.time() + max(0.1, timeout)
        raw = self._next_raw(deadline)
        grams = (raw - self._offset_raw) * self._factor
        if not math.isfinite(grams):
            raise SensorDataError("Sensor returned a non-finite value.")
        return self._reading(round(grams, 2), round(raw, 2))

    def tare(self, samples: int = 10) -> Reading:
        if not self._connected:
            self.connect()
        deadline = time.time() + max(1.0, self.settings.sensor_timeout_s) + 0.3 * samples
        values = [self._next_raw(deadline) for _ in range(max(1, samples))]
        with self._lock:
            self._offset_raw = mean(values)
            self._history.clear()
        try:
            self._send("TARE")
        except SensorError:
            pass  # host-side offset is authoritative anyway
        self._last_message = f"Tare complete (offset={self._offset_raw:.1f} counts)."
        return self._reading(0.0, self._offset_raw, self._last_message)

    def calibrate(self, reference_weight_g: float, samples: int = 20) -> float:
        if reference_weight_g <= 0:
            raise ValueError("Reference weight must be > 0 g")
        if not self._connected:
            self.connect()
        deadline = time.time() + max(2.0, self.settings.sensor_timeout_s) + 0.3 * samples
        values = [self._next_raw(deadline) for _ in range(max(5, samples))]
        raw_mean = mean(values)
        numerator = raw_mean - self._offset_raw
        if pstdev(values) > max(50.0, abs(numerator) * 0.1):
            raise SensorDataError(
                "Raw readings are too noisy to calibrate — secure the reference "
                "weight and retry."
            )
        if abs(numerator) < 1e-6:
            raise SensorDataError(
                "Reading equals the tare offset — remove the platform load and tare "
                "again before calibrating."
            )
        factor = float(reference_weight_g) / numerator
        with self._lock:
            self._factor = factor
            self._calibrated = True
            self._calibration_meta = {
                "reference_weight_g": float(reference_weight_g),
                "raw_reading_at_calibration": raw_mean,
                "factor": factor,
                "simulated": False,
            }
        try:
            self._send(f"CAL,{factor:.6f}")
        except SensorError:
            pass
        self._last_message = f"Calibrated with {reference_weight_g:g} g reference."
        return factor

    @property
    def calibration_meta(self) -> dict:
        return dict(self._calibration_meta)


# --------------------------------------------------------------------------- factory
def create_sensor(settings: Settings) -> WeightSensor:
    """Build the configured sensor backend (never raises)."""
    backend = (settings.sensor_backend or "mock").lower()
    if backend == "serial":
        sensor: WeightSensor = SerialHX711Sensor(settings)
        try:
            if settings.sensor_port:
                sensor.connect()
        except SensorError as exc:
            sensor._last_message = str(exc)  # surface reason via status()
    elif backend == "disabled":
        sensor = WeightSensor(settings)
        sensor._last_message = "Sensor disabled by configuration."
    else:
        sensor = MockWeightSensor(settings)
        sensor.connect()
    return sensor
