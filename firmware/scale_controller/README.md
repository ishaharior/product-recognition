# Scale controller firmware

Arduino Uno/Nano/ESP32 sketch driving an **HX711** load-cell amplifier and streaming
raw counts to the Smart Product Station backend over USB serial.

See [docs/HARDWARE_SETUP.md](../../docs/HARDWARE_SETUP.md) for wiring, flashing,
the serial protocol, and tare/calibration instructions.

## Quick reference

- **Baud:** 9600, newline-terminated lines.
- **Pins:** SCK → D4/GPIO4, DOUT → D5/GPIO5.
- **Out:** `RAW,<counts>` (~8 Hz), `OK,<msg>`, `ERR,<msg>`, `BOOT,smart-station-scale,1.0.0`
- **In:** `TARE`, `CAL,<factor>`, `PING`
- **Library:** bogde HX711 (Arduino Library Manager).

The firmware deliberately contains no gram maths beyond passing `CAL` values —
the host computes `grams = (RAW − tare_offset) × factor`.
