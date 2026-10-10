"""Mock sensor: readings, tare, calibration, stability, units, factories.

Hardware tests: only mock + serial *protocol parsing* run here (the serial
port itself is stubbed). Real HX711 hardware is NOT exercised by this suite.
"""

from __future__ import annotations

import dataclasses
import time

import pytest

from app.core.config import load_settings
from src.sensors.weight_sensor import (
    MockWeightSensor,
    SensorConnectionError,
    SensorDataError,
    SerialHX711Sensor,
    WeightSensor,
    convert_units,
    create_sensor,
)


@pytest.fixture()
def settings():
    return load_settings()


@pytest.fixture()
def sensor(settings):
    s = MockWeightSensor(settings, seed=7)
    s.connect()
    yield s
    s.disconnect()


def test_mock_reading_is_labelled_simulated(sensor):
    sensor.set_weight(250.0)
    reading = sensor.read()
    assert reading.source == "simulated"
    assert reading.grams is not None
    assert abs(reading.grams - 250.0) < 5.0  # gaussian noise, sigma=0.4
    assert sensor.status()["simulated"] is True
    assert "not a real" in reading.message.lower()


def test_mock_zero_platform_reads_near_zero(sensor):
    sensor.set_weight(0.0)
    readings = [sensor.read().grams for _ in range(5)]
    assert all(g is not None and abs(g) < 3.0 for g in readings)


def test_stability_window(sensor):
    sensor.set_weight(100.0)
    for _ in range(6):
        reading = sensor.read()
    assert reading.stable is True
    assert sensor.status()["stable"] is True

    # A jump invalidates stability until new samples settle.
    sensor.set_weight(600.0)
    reading = sensor.read()
    assert reading.stable is False


def test_wait_for_stable(sensor):
    sensor.set_weight(320.0)
    reading = sensor.wait_for_stable(timeout=2.0, interval=0.01)
    assert reading.stable is True
    assert abs(reading.grams - 320.0) < 6.0


def test_tare_and_calibration_self_consistency(sensor):
    """Mock calibration keeps readings accurate (simulation stays honest)."""
    sensor.set_weight(0.0)
    sensor.tare(samples=5)
    factor = sensor.calibrate(500.0, samples=8)
    assert factor > 0
    assert sensor.calibrated is True

    sensor.set_weight(250.0)
    reading = sensor.read()
    assert abs(reading.grams - 250.0) < 8.0
    assert reading.source == "simulated"


def test_calibration_rejects_zero_reference(sensor):
    with pytest.raises(ValueError):
        sensor.calibrate(0.0)


def test_unit_conversion():
    assert convert_units(1500.0, "kg") == 1.5
    assert convert_units(1500.0, "g") == 1500.0
    assert convert_units(None, "kg") is None
    with pytest.raises(ValueError):
        convert_units(10.0, "lbs")


def test_reading_format(sensor):
    sensor.set_weight(1500.0)
    assert sensor.read().format().endswith("kg")
    sensor.set_weight(250.0)
    assert sensor.read().format().endswith("g")


def test_create_sensor_factory(settings):
    mock = create_sensor(settings)
    assert isinstance(mock, MockWeightSensor)
    assert mock.connected is True
    mock.disconnect()

    disabled = create_sensor(dataclasses.replace(settings, sensor_backend="disabled"))
    assert isinstance(disabled, WeightSensor)
    assert disabled.backend == "disabled"
    assert disabled.status()["connected"] is False


def test_serial_sensor_without_port_raises(settings):
    sensor = SerialHX711Sensor(dataclasses.replace(settings, sensor_port=""))
    with pytest.raises(SensorConnectionError):
        sensor.connect()


def test_serial_sensor_bad_port_raises(settings):
    sensor = SerialHX711Sensor(dataclasses.replace(settings, sensor_port="COM9999"))
    with pytest.raises(SensorConnectionError):
        sensor.connect()
    assert sensor.connected is False


def test_serial_line_protocol_parsing(settings):
    """RAW/OK/ERR line handling with a stubbed serial read."""
    sensor = SerialHX711Sensor(dataclasses.replace(settings, sensor_port="COM1"))
    sensor._connected = True  # bypass physical port

    lines = iter(["BOOT,smart-station-scale,1.0.0", "OK,ready", "RAW,1234.5"])
    sensor._readline = lambda deadline: next(lines)  # type: ignore[method-assign]
    assert sensor._next_raw(time.time() + 1) == 1234.5

    sensor._readline = lambda deadline: "RAW,not-a-number"  # type: ignore[method-assign]
    with pytest.raises(SensorDataError):
        sensor._next_raw(time.time() + 1)

    sensor._readline = lambda deadline: "ERR,sensor not ready"  # type: ignore[method-assign]
    with pytest.raises(SensorDataError):
        sensor._next_raw(time.time() + 1)


def test_serial_read_converts_raw_to_grams(settings):
    sensor = SerialHX711Sensor(dataclasses.replace(settings, sensor_port="COM1"))
    sensor._connected = True
    sensor._factor = 2.0
    sensor._offset_raw = 10.0

    sensor._readline = lambda deadline: "RAW,500"  # type: ignore[method-assign]
    reading = sensor.read(timeout=0.5)
    assert reading.grams == pytest.approx((500.0 - 10.0) * 2.0, abs=0.01)
    assert reading.source == "real"  # serial backend is never simulated


def test_disabled_sensor_status(settings):
    sensor = create_sensor(dataclasses.replace(settings, sensor_backend="disabled"))
    status = sensor.status()
    assert status["backend"] == "disabled"
    assert "disabled" in status["message"].lower()
