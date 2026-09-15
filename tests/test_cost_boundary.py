"""Guard 2 of the cost boundary (technical_architecture.md §6, CLAUDE.md non-negotiable 1).

Importing the free-tier web app must not, transitively, import any metered client
or the Layer 2 generation package. This is a runtime import-graph check that
complements the static import-linter contract in pyproject.toml.
"""

import importlib
import subprocess
import sys

METERED_MODULES = ("anthropic", "atsc.deep.generation", "atsc.deep.worker")


def test_importing_free_app_does_not_load_metered_modules() -> None:
    # Run in a fresh interpreter so this test's own imports don't pollute sys.modules.
    code = (
        "import sys, json; import atsc.web.app; import atsc.free; "
        f"print(json.dumps(sorted(m for m in sys.modules if m in {METERED_MODULES!r})))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    loaded = out.stdout.strip()
    assert loaded == "[]", f"metered modules reachable from free path: {loaded}"


def test_free_package_is_importable_without_an_api_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    importlib.import_module("atsc.free")
    importlib.import_module("atsc.web.app")


def test_generation_module_is_where_the_metered_client_lives() -> None:
    """Positive control: the forbidden module really does import the SDK, so the contract bites."""
    code = "import sys, atsc.deep.generation; print('anthropic' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "True"
