# Sanitized Examples

These files are intentionally generic and contain no real MAC addresses, passwords, hosts, entity IDs or dashboards from a personal installation.

## Files

- `configuration.example.yaml`
  Minimal Home Assistant configuration showing how to include `myhome.yaml`, packages and YAML dashboards.
- `myhome.example.yaml`
  Generic multi-gateway MyHOME setup with lights, shutters, thermoregulation, load control, scene programmer, alarm panel, lighting management and video.
- `secrets.example.yaml`
  Placeholders for values that should never be committed.
- `packages/`
  Reusable patterns for Google Home bridges, service wrappers and scenario status sensors.
- `lovelace/`
  YAML dashboards for audio/radio and thermoregulation.
- `google_assistant/`
  Example `entity_config` entries for exposing MyHOME entities safely.

## Usage

1. Copy the files you need into your Home Assistant config directory.
2. Replace placeholder values such as MAC addresses, hosts and entity IDs.
3. Keep real credentials in `secrets.yaml` or UI-managed config entries, never in git.

## Placeholders used here

- `00:03:50:AA:BB:CC` and similar values are fake MAC addresses.
- `YOUR_*` values are placeholders only.
- Example entity IDs are intentionally generic and may differ from your installation.
