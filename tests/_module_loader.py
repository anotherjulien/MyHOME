from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name: str):
    module_path = REPO_ROOT / "custom_components" / "myhome" / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(f"tests.{module_name}", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module {module_name} from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
