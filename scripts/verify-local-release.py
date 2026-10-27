"""Run the focused release gate locally once, without installing dependencies.

Use the existing application Python and a Node 20+ executable. Tests receive
throwaway data directories; no private library or model weights are accessed.
A failed step stops the run. Retrying requires an explicit new invocation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

PYTHON_TESTS = [
    "tests/test_directml_local.py", "tests/test_studio_local.py",
    "tests/test_complete_multitrack_local.py", "tests/test_processing_progress.py",
    "tests/test_ui_store.py", "tests/test_karaoke_timing.py",
    "tests/test_karaoke_service.py", "tests/test_karaoke_delete_model.py",
]
JS_TESTS = [
    "studio-lanes", "multitrack-playback", "wav-header", "audio-routing",
    "theme", "shared-ui-store", "karaoke-timing-ui", "karaoke",
    "processing-selection", "setlist", "song-setlist",
]


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--node", default=shutil.which("node"))
    parser.add_argument("--report-dir", required=True, type=Path)
    options = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    report_dir = options.report_dir.resolve()
    if report_dir.exists():
        raise SystemExit("Use a new report directory; previous evidence is never overwritten.")
    if not options.node:
        raise SystemExit("Node.js is required; specify --node. No dependency is installed automatically.")
    if subprocess.run(["git", "-C", str(root), "diff", "--quiet", "HEAD"]).returncode:
        raise SystemExit("Commit reviewed tracked changes before validating an exact revision.")
    revision = git(root, "rev-parse", "HEAD")
    report_dir.mkdir(parents=True)
    data = report_dir / "private-scratch"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("STEMDECK_", "N3LX_"))}
    for name, subdir in {"DATA": "data", "JOBS": "jobs", "CACHE": "cache", "MODELS": "models", "LOGS": "logs", "DOWNLOADS": "downloads"}.items():
        env[f"STEMDECK_{name}_DIR"] = str(data / subdir)
    env.update({"STEMDECK_DEMUCS_DEVICE": "cpu", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    result = {"revision": revision, "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "platform": platform.platform(), "execution": "local", "hosted_ci": False,
              "private_library_used": False, "real_models_run": False, "steps": [], "passed": False}

    def run(name, command, timeout=180):
        started = time.monotonic()
        try:
            process = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True,
                                     encoding="utf-8", errors="replace", timeout=timeout)
            code, output = process.returncode, process.stdout + process.stderr
        except subprocess.TimeoutExpired as exc:
            code, output = 124, f"Bounded timeout: {exc.timeout} seconds"
        (report_dir / (name + ".log")).write_text(output, encoding="utf-8")
        result["steps"].append({"name": name, "exit_code": code, "seconds": round(time.monotonic() - started, 3)})
        print(f"{name}: {'PASS' if code == 0 else 'FAIL'} (exit {code})", flush=True)
        if code:
            raise RuntimeError(f"{name} failed; see its local log. No retry was attempted.")
        return output

    failure = None
    try:
        result["python"] = run("python-version", [options.python, "--version"]).strip()
        result["node"] = run("node-version", [options.node, "--version"]).strip()
        if int(result["node"].lstrip("v").split(".")[0]) < 20:
            raise RuntimeError("Node 20 or newer is required.")
        run("diff-check", ["git", "diff", "--check", "HEAD^", "HEAD"])
        run("pytest", [options.python, "-m", "pytest", *PYTHON_TESTS, "-q", "--tb=short",
                       "--junitxml=" + str(report_dir / "pytest.xml")], timeout=300)
        tree = ET.parse(report_dir / "pytest.xml")
        suites = list(tree.getroot().iter("testsuite"))
        result["python_tests"] = {key: sum(int(s.attrib.get(key, 0)) for s in suites)
                                  for key in ("tests", "failures", "errors", "skipped")}
        run("javascript-tests", [options.node, "--test", *[f"tests/js/{name}.test.mjs" for name in JS_TESTS]], timeout=180)
        result["javascript_files"] = len(JS_TESTS)
        for source in ("desktop-app/main.cjs", "desktop-app/preload.cjs", "static/js/theme.js",
                       "static/js/themeBoot.js", "static/js/confirmAction.js", "static/js/catalog.js", "static/js/lyrics.js"):
            run("syntax-" + Path(source).stem, [options.node, "--check", source])
        if git(root, "rev-parse", "HEAD") != revision:
            raise RuntimeError("HEAD changed during validation; results cannot authorize a different revision.")
        result["passed"] = True
    except Exception as exc:
        failure = str(exc)
        result["failure"] = failure
    finally:
        result["ended_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        (report_dir / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        state = "PASS" if result["passed"] else "FAIL"
        counts = result.get("python_tests", {})
        report = (f"# Local release validation: {state}\n\n"
                  f"Commit: `{revision}`\n\nExecution: local Windows; no hosted CI run is claimed.\n\n"
                  f"Python test cases: {counts.get('tests', 'not completed')}; "
                  f"skipped: {counts.get('skipped', 0)}.\n\n"
                  f"JavaScript test files: {result.get('javascript_files', 'not completed')}.\n\n"
                  "No dependency installation, real-model execution, private library access or automatic retry.\n")
        if failure:
            report += "\nFailure: " + failure + "\n"
        (report_dir / "RESULT.md").write_text(report, encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
