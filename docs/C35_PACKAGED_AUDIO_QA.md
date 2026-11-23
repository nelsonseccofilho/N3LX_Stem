# C35.1 — Packaged Windows audio and native export QA

C32/C33 validated audio transport and the WAV/MP4 backend using synthetic
jobs. C34 validated the packaged Windows EXE, native window size, profile,
reopen and cooperative backend shutdown.

C35 specifically validates Play from the packaged executable, the native
Export Mix WAV download triggered through the real menu, and closing the app
while audio is playing. The existing C34 Bash harness builds the package,
verifies the manifest and runs an authenticated safe teardown. A distinct mode
runs only C35, not the previously approved C34 resizing suite.

From an isolated, clean C35 worktree, in Git Bash:

    N3LX_C34_RUNTIME="$HOME/Git/N3LX_Stem" bash scripts/qa/c35-audio.sh

The job is a 2-second synthetic sine tone in an isolated data directory and
on a new QA port. The Electron download manager saves only the expected
synthetic mix to a new isolated exports directory. User Downloads and the
personal music library are not modified. Never stop an unknown or busy
process; the existing helper verifies the port's release.

Automated gate: actual Play moves the transport, native export returns a
valid stereo WAV verified by FFprobe, the packaged window can close while
playing, audio-qa.json.passed is true, and the outer teardown reports an
authenticated safe stop or a verified free port.

Manual Windows hardware gate remains separate: user must listen to tones
through speakers/headphones and verify real audibility, sound quality and
what happens when the Windows default device changes. No native in-app
device selector has been verified. Programmatic audio clock success must
never be reported as physical audio success. MP4 GUI exports, long tracks,
real AMD GPU inference and personal-library playback remain out of scope.
