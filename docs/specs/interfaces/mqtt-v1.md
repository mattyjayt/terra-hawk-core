---
id: IF-MQTT-V1
title: MQTT contract v1
status: Draft
owner: Argos (draft) · Jaime (approver)
updated: 2026-10-30
---

# IF-MQTT-V1 — MQTT contract
Broker: HiveMQ Cloud, TLS 8883, one credential per device.

## Topic tree
```
terrahawk/v1/{system_id}/{device_id}/telemetry   # device → cloud, QoS 1
terrahawk/v1/{system_id}/{device_id}/state       # retained, LWT "offline"
terrahawk/v1/{system_id}/{device_id}/event       # discrete events, QoS 1
terrahawk/v1/{system_id}/{device_id}/cmd         # cloud → device, QoS 1
```
System ids: `chamber-01`, `rack-01`, `scout-01`.

## Telemetry payload
```json
{"ts": 1761830400000, "fw": "1.0.0", "readings": {"temperature_c": 22.4, "humidity_pct": 61.0, "pressure_hpa": 1012.3, "ph": 6.1}}
```
| Key | Unit | Source |
|---|---|---|
| temperature_c | °C | BME280 |
| humidity_pct | % | BME280 |
| pressure_hpa | hPa | BME280 |
| ph | — | DFRobot pH V2 |
| ec_ms_cm | mS/cm | future |
| water_level_pct | % | future |
| soil_pct | % | capacitive soil sensor |
| light_lux | lux | future |
| battery_v | V | Scout |
Retired keys: `h2o`, `water`, `soil`, `temp`, `hum`.

## State / event / cmd
- state: `{"status":"online|offline","fw":"1.0.0","uptime_s":1234,"rssi":-61}`
- event: `{"ts":…, "kind":"pump_on|pump_off|low_water|sensor_fault", "data":{…}}`
- cmd: `{"id":"<uuid>","action":"pump","params":{"on":true,"ms":5000}}` → the device answers on `event` with `{"kind":"cmd_ack","data":{"id":"<uuid>","ok":true}}`
