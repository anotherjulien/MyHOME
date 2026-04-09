# Extended OpenWebNet Services

This repository now exposes a larger set of protocol helpers as typed Home Assistant services instead of forcing users to send raw OpenWebNet frames.

## Service families

- `gateway_request` and `gateway_command`
  WHO=13 readbacks and date/time writes with structured output for time, date, MAC, IP, firmware and uptime.
- `scenario_command`
  WHO=0 scenario activation, recording, erase and lock helpers.
- `cen_command` and `cenplus_command`
  WHO=15 and WHO=25 virtual button actions for scenarios and custom bridges.
- `alarm_request` and `aux_command`
  WHO=5 status requests and WHO=9 auxiliary channel controls.
- `audio_zone_command`, `audio_general_command`, `audio_source_command`, `audio_radio_command`
  WHO=22 helpers for zone audio, radio, source control and advanced readbacks.
- `scene_programmer_command`
  WHO=17 controls for devices such as MH200N.
- `video_command`
  WHO=7 multimedia and video door entry commands.
- `light_management_request` and `light_management_command`
  WHO=24 lighting-management reads and writes.
- `energy_request`
  WHO=18 structured metering and historical requests.
- `thermo_zone_command`, `thermo_central_command`, `thermo_request`, `thermo_split_set`
  Advanced WHO=4 and WHO=1004 thermoregulation helpers.

## Where to look next

- Full field-level schemas: `custom_components/myhome/services.yaml`
- Generic configuration snippets: `examples/myhome.example.yaml`
- Reusable Home Assistant packages and dashboards: `examples/`
- Lightweight parser tests: `tests/`
