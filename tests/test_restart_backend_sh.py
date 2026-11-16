import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which("bash"), reason="Git Bash unavailable")
def test_bash_runs_gate_in_order_and_stops_on_failure(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/restart-backend.sh"
    source = script.read_text(encoding="utf-8").lower()
    assert "powershell" not in source and "pwsh" not in source and ".ps1" not in source
    fake = tmp_path / "python"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        'printf \'%s\\n\' "$2" >> "$N3LX_TEST_LOG"\n'
        'if [[ "$2" == "${N3LX_TEST_FAIL:-none}" ]]; then exit 7; fi\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    log = tmp_path / "calls.txt"
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "N3LX_TEST_LOG": str(log),
        "N3LX_RUNTIME": str(tmp_path),
        "N3LX_DATA": str(tmp_path),
        "N3LX_PORT": "8160",
    }
    for failing, expected in [
        ("check-ready", ["check-ready"]),
        ("stop", ["check-ready", "stop"]),
        ("verify-free", ["check-ready", "stop", "verify-free"]),
        ("start", ["check-ready", "stop", "verify-free", "start"]),
        ("none", ["check-ready", "stop", "verify-free", "start", "status"]),
    ]:
        log.unlink(missing_ok=True)
        result = subprocess.run(
            [shutil.which("bash"), str(script)],
            env={**env, "N3LX_TEST_FAIL": failing},
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == (0 if failing == "none" else 7)
        assert log.read_text(encoding="utf-8").splitlines() == expected
