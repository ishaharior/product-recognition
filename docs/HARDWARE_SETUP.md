# Hardware setup — weighing scale

The station reads a load cell through an **HX711 amplifier** driven by the
microcontroller sketch in `firmware/scale_controller/`. Without hardware, set
`SENSOR_BACKEND=mock` (default) — everything works with simulated stable readings.

## Bill of materials

- Load cell (e.g. 1 kg / 5 kg strain-gauge bar or plate cell) + HX711 module
- Arduino Uno/Nano **or** ESP32, USB cable
- Jumper wires; a rigid stage/platform to mount the cell

## Wiring (HX711)

| HX711 pin | Arduino Uno/Nano | ESP32 |
| --------- | ---------------- | ----- |
| VCC | 5V | 3V3 |
| GND | GND | GND |
| SCK | D4 | GPIO4 |
| DOUT | D5 | GPIO5 |

Load-cell wires follow the HX711 module's A+/A−/B+/B− labels (red/black/white/green —
order varies by cell; if the reading goes the wrong way, swap A+/A−).

## 1. Flash the firmware

1. Open `firmware/scale_controller/scale_controller.ino` in the Arduino IDE
   (or PlatformIO / `arduino-cli`).
2. Install the **HX711** library (bogde/HX711) via the Library Manager.
3. Select your board + port, compile, upload.
4. Open the Serial Monitor at **9600 baud** — you should see:
   `BOOT,smart-station-scale,1.0.0` then `OK,hx711 ready` (or `ERR,hx711 not found - check SCK/DOUT wiring`).

### Serial protocol (9600 baud, newline-terminated)

| Direction | Line | Meaning |
| --------- | ---- | ------- |
| device → host | `RAW,<counts>` | raw reading, every ~120 ms |
| device → host | `OK,<message>` / `ERR,<message>` | acknowledgement / error |
| device → host | `BOOT,smart-station-scale,<ver>` | startup banner |
| host → device | `TARE` | zero at current load (empty scale!) |
| host → device | `CAL,<factor>` | store calibration factor (grams/count) |
| host → device | `PING` | expect `OK,PONG` |

The host computes `grams = (RAW − tare_offset) × factor` — the Python side is the
single source of truth for calibration maths; the firmware only streams counts.

## 2. Connect the backend

```powershell
Copy-Item .env.example .env
# edit .env:
#   SENSOR_BACKEND=serial
#   SENSOR_PORT=COM3          # Device Manager → Ports (COM & LPT)
#   SENSOR_BAUDRATE=9600
python -m uvicorn app.main:app --app-dir backend --port 8000
```

Check `GET /api/sensor/status` — `connected: true` and the port/baud reported.

## 3. Tare and calibrate

1. **Tare** with the platform empty:
   ```powershell
   Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/sensor/tare
   ```
2. **Calibrate** with a known reference mass on the cell (e.g. a 100 g test weight):
   ```powershell
   Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/sensor/calibrate `
       -ContentType 'application/json' `
       -Body '{"reference_weight_g": 100, "samples": 20}'
   ```
   The computed factor is stored (and recorded in the `sensor_calibrations` table).
3. Verify:
   ```powershell
   Invoke-RestMethod http://127.0.0.1:8000/api/sensor/reading
   # weight_g ≈ 100, stable = true
   ```

Stability requires the reading to stay within `SENSOR_STABILITY_DELTA_G` for
`SENSOR_STABILITY_SAMPLES` samples over `SENSOR_STABILITY_WINDOW_S` seconds.

## Troubleshooting

| Symptom | Likely cause / fix |
| ------- | ------------------ |
| `No serial port configured` | set `SENSOR_PORT=COMx` in `.env` |
| `PermissionError` opening port | Serial Monitor / another app holds the port — close it |
| `No data from COMx within timeout` | wrong baud (must be 9600) or wrong port; re-plug and re-check Device Manager |
| `ERR,hx711 not found` on boot | SCK/DOUT wiring; power cycle after re-wiring |
| Readings drift | let the cell warm up 15 min; re-tare; check mechanical mounting |
| Plausible but wrong weight | re-run calibration with an accurately known reference mass |

> **Honest note:** only the *mock* sensor path is covered by the automated tests.
> The serial path is implemented per the protocol above but must be validated on
> real hardware — no hardware test run is claimed in this repository's test results.
