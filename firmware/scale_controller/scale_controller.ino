/*
 * Smart Product Station — scale controller firmware
 * Target: Arduino Uno / Nano / ESP32 with an HX711 load-cell amplifier.
 *
 * Protocol (USB serial, 9600 baud by default):
 *   Device -> Host:  RAW,<counts>\n      streamed every SERIAL_INTERVAL_MS
 *                    OK,<message>\n      command acknowledgement
 *                    ERR,<message>\n     error report
 *                    BOOT,smart-station-scale,<version>\n  startup banner
 *   Host -> Device:  TARE\n              zero at current load
 *                    CAL,<factor>\n      store calibration factor (grams/count)
 *                    PING\n             expect OK,PONG
 *
 * Wiring (HX711):
 *   HX711 VCC  -> 5V (Arduino) / 3V3 (ESP32)
 *   HX711 GND  -> GND
 *   HX711 SCK  -> D4 (Arduino) / GPIO4 (ESP32)
 *   HX711 DOUT -> D5 (Arduino) / GPIO5 (ESP32)
 *
 * The host applies: grams = (RAW - tare_offset) * calibration_factor.
 * This firmware only streams raw counts and accepts TARE/CAL/PING so the
 * Python side stays the single source of truth for calibration maths.
 */

#define FW_VERSION "1.0.0"

#if defined(ESP32)
  #define PIN_SCK  4
  #define PIN_DOUT 5
#else
  #define PIN_SCK  4
  #define PIN_DOUT 5
#endif

#include <HX711.h>

#ifndef SERIAL_INTERVAL_MS
  #define SERIAL_INTERVAL_MS 120  // ~8 readings/second
#endif

HX711 scale;
unsigned long lastStream = 0;
float calibrationFactor = 1.0;  // informational; host recomputes on CAL

void setup() {
  Serial.begin(9600);
  while (!Serial && millis() < 3000) { /* wait for USB serial on ESP32 */ }

  scale.begin(PIN_DOUT, PIN_SCK);
  if (scale.is_ready()) {
    scale.set_scale(calibrationFactor);
    Serial.println(F("BOOT,smart-station-scale,") FW_VERSION);
    Serial.println(F("OK,hx711 ready"));
  } else {
    Serial.println(F("BOOT,smart-station-scale,") FW_VERSION);
    Serial.println(F("ERR,hx711 not found - check SCK/DOUT wiring"));
  }
}

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd.equalsIgnoreCase("TARE")) {
    if (!scale.is_ready()) { Serial.println(F("ERR,cannot tare - sensor not ready")); return; }
    scale.tare(10);
    Serial.println(F("OK,tare complete"));
  } else if (cmd.equalsIgnoreCase("PING")) {
    Serial.println(F("OK,PONG"));
  } else if (cmd.startsWith("CAL,")) {
    String value = cmd.substring(4);
    value.trim();
    float factor = value.toFloat();
    if (factor == 0.0) { Serial.println(F("ERR,invalid CAL factor")); return; }
    calibrationFactor = factor;
    scale.set_scale(calibrationFactor);
    Serial.print(F("OK,calibration factor "));
    Serial.println(factor, 6);
  } else {
    Serial.print(F("ERR,unknown command: "));
    Serial.println(cmd);
  }
}

void loop() {
  while (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    handleCommand(line);
  }

  unsigned long now = millis();
  if (now - lastStream >= SERIAL_INTERVAL_MS) {
    lastStream = now;
    if (scale.is_ready()) {
      long raw = scale.get_value(1);  // raw counts minus device tare offset
      Serial.print(F("RAW,"));
      Serial.println(raw);
    } else {
      Serial.println(F("ERR,sensor not ready"));
      delay(500);
    }
  }
}
