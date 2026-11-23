import asyncio
import importlib.util
from pathlib import Path

import pytest

runner_path = Path(__file__).parents[2] / "scripts" / "run_integration_tests.py"
runner_spec = importlib.util.spec_from_file_location("run_integration_tests", runner_path)
assert runner_spec and runner_spec.loader
runner = importlib.util.module_from_spec(runner_spec)
runner_spec.loader.exec_module(runner)


def test_integration_runner_refuses_remote_database() -> None:
    with pytest.raises(ValueError, match="only recreate the local attackpath_test"):
        asyncio.run(
            runner.recreate_database(
                # pragma: allowlist nextline secret
                "postgresql://app:secret@db.example.com:5432/attackpath_test"
            )
        )
