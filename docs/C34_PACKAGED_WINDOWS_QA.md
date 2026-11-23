# C34.1 — Packaged Windows native QA

The previous C32/C33 results validate the Electron development shell, renderer
dimensions and synthetic playback/export APIs. The candidate Windows update
is different: an EXE bundled with resources, using an existing AMD installation.

Run in a CLEAN C34 branch worktree from Git Bash:

    N3LX_C34_RUNTIME="$HOME/Git/N3LX_Stem" bash scripts/qa/c34-packaged.sh

The script creates a new C34-Windows-XXXXXXXX evidence directory outside Git
containing a package built from the exact worktree commit, synthetic jobs,
a separate exports folder, a separate Electron userData profile and test logs.
It does not install dependencies, replace an existing package or move a library.

The test runs the actual packaged N3LX_Stem.exe, which starts its own
authenticated backend using the existing packaged launcher. The terminal only
runs Git Bash; no manual CMD/PowerShell commands are necessary.

It verifies the manifest, package revision, no bundled private data, backend
identity, exactly two synthetic jobs, native BrowserWindow resizing with
setSize (not fake page.setViewportSize), appearance IPC, and reopen with the
same isolated export preference. The preference is deliberately preseeded
in the temporary profile: this is NOT a test of clicking the native folder
picker. A successful run still does NOT prove an installed MSI/setup,
hardware-audible playback, device switching, long exports or AMD/Vulkan
inference. Those are separate acceptance gates.

The shell identifies the packaged backend by the authenticated control file,
waits for idle, stops cooperatively, and verifies the QA port is released.
If a process is busy or foreign, the QA fails and does not force-stop it.
Protect port 8159 and the real jobs, cache, playlists and settings.

Require native-qa.json passed:true and teardown PASS for C34.1 acceptance.
GitHub hosted skipped jobs never count as passed.
