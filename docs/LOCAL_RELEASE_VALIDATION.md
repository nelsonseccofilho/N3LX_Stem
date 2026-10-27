# Release validation without a paid hosted runner

GitHub Actions is optional for this repository. Release approval can use the
existing Windows installation and a local report bound to an exact commit.
The owner requested this route because hosted jobs are blocked by account
billing. No branch protection, ruleset or security setting is disabled.
The N3LX workflow is manual-only; it remains available when explicitly wanted.
No green hosted status is fabricated and no billing limit is worked around.

## Local gate

From an isolated checkout with reviewed, committed changes:

```powershell
& <existing-python.exe> scripts/verify-local-release.py `
  --python <existing-python.exe> --node <existing-node.exe> `
  --report-dir <new-temporary-report-directory>
```

The script installs nothing. It redirects all app data/cache/jobs/model paths
into scratch directories, runs one bounded pass, stops on a failure, and records
exit codes, runtime versions and HEAD. It covers the Python tests and JS tests
from N3LX checks plus the appearance, karaoke and playlist regressions. It does
not execute real ML weights or use personal audio. Unit-test CPU stubs do not
change the production AMD-first configuration.

Keep raw logs and scratch private. Attach only RESULT.md and summary.json to the
review/release evidence. Those reports explicitly identify local execution.
A passing local gate plus the recorded Windows/browser/package QA supports code
integration. It does not substitute for a listening/acceptance test of complete
sung lyrics, a complete extraction, Linux/macOS validation, or a clean-machine
ML installation. The published Windows update requires the existing AMD runtime.

## Review and merge

Record the validated commit and results in the PR description. Confirm HEAD has
not moved and use that exact expected head for merge. Do not bypass a required
check or modify protection rules: inspect the actual repository rules first.
A hosted job that never started remains unavailable, not passed. If local tests
fail, repair the cause before a focused verification; do not loop until green.
