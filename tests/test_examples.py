from __future__ import annotations

import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"


class ExampleLoader(yaml.SafeLoader):
    pass


def _construct_passthrough(loader, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


for tag in ("!include", "!include_dir_named", "!include_dir_merge_named"):
    ExampleLoader.add_constructor(tag, _construct_passthrough)


def test_all_example_yaml_files_parse():
    yaml_files = sorted(EXAMPLES_DIR.rglob("*.yaml"))
    assert yaml_files, "No example YAML files found."

    for path in yaml_files:
        with path.open("r", encoding="utf-8") as handle:
            yaml.load(handle, Loader=ExampleLoader)


def test_audio_dashboard_example_is_present_and_contains_radio_controls():
    path = EXAMPLES_DIR / "lovelace" / "dashboard_audio.example.yaml"
    with path.open("r", encoding="utf-8") as handle:
        dashboard = yaml.load(handle, Loader=ExampleLoader)

    payload = json.dumps(dashboard)
    assert "sensor.audio_radio_radio_frequency" in payload
    assert "button.audio_radio_radio_query_status" in payload
