#!/usr/bin/env bash
# C35.2 manual acoustic acceptance in one safe, isolated Windows session.
# Git Bash only. This does NOT rerun C32-C35.1 and never touches user jobs.
set -euo pipefail

worktree="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
runtime="$HOME/Git/N3LX_Stem"
release="$HOME/Git/N3LX_Stem-Releases"
source_report="$release/C35-Audio-Iosa3kSK"
python="$runtime/.venv/Scripts/python.exe"
merged_base="840d3918de8562b756456f675946f9e29d7000c0"
packaged_source="80182ad489b75b909e370f94c9bdbd32ffef12b2"

echo '=== C35.2 — CHECKS E AUDICAO EM UMA SESSAO ==='
test -f "$python"
test -f "$runtime/.venv-directml/Scripts/python.exe"
test -z "$(git -C "$worktree" status --porcelain)"
git -C "$worktree" merge-base --is-ancestor "$merged_base" HEAD
git -C "$runtime" merge-base --is-ancestor "$merged_base" HEAD
test -d "$release"
test -d "$source_report/bundle"

version="$("$python" -B -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8"))["version"])' "$runtime/desktop-app/package.json")"
package="$source_report/bundle/N3LX_Stem-Windows-Update-$version"
exe="$package/N3LX_Stem.exe"
test -f "$exe"
test -f "$package/resources/stemdeck/scripts/backend_control.py"

# Source report is the already-approved C35.1 packaged binary. Verify it
# instead of rebuilding or executing any previous QA cycle.
"$python" -B - "$package" "$packaged_source" <<'PY'
import hashlib, json, sys
from pathlib import Path
pkg = Path(sys.argv[1])
info = json.loads((pkg / "build-info.json").read_text(encoding="utf-8"))
assert info["source_revision"] == sys.argv[2], "wrong C35.1 packaged revision"
assert info["kind"] == "update-requires-existing-amd-installation"
manifest = json.loads((pkg / "sha256-manifest.json").read_text(encoding="utf-8"))
digest = hashlib.sha256()
with (pkg / "N3LX_Stem.exe").open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
assert digest.hexdigest() == manifest["N3LX_Stem.exe"], "EXE manifest mismatch"
print("PASS: pacote C35.1 original conferido sem rebuild")
PY

report="$(mktemp -d "$release/C35-ListeningBatch-XXXXXXXX")"
mkdir -p "$report/data/jobs" "$report/profile" "$report/exports"
port="$(node "$worktree/scripts/qa/available-port.mjs")"
case "$port" in 8159|8162) echo 'BLOCKED: protected port chosen' >&2; exit 1 ;; esac

qa_backend() {
  "$python" -B "$package/resources/stemdeck/scripts/backend_control.py" "$1" \
    --port "$port" --runtime "$runtime" --data "$report/data"
}
source "$worktree/scripts/qa/c34-teardown.sh"

gui_closed=0
cleanup() {
  local code=$?
  trap - EXIT
  echo
  echo '=== C35.2 — FINALIZACAO SEGURA ==='
  if [[ "$gui_closed" == 1 ]]; then
    if ! c34_safe_teardown "$report"; then code=1; fi
  else
    # An interrupted session may have a live window. Never shut down its
    # server from a blind EXIT trap, even when it currently reports idle.
    if ! qa_backend verify-free > "$report/verify-interrupted.log" 2>&1; then
      echo 'BLOCKED: janela nao confirmada fechada. Feche o EXE normalmente.' >&2
      echo 'Nenhum processo foi encerrado a forca.' >&2
      code=1
    else
      echo 'PASS: porta QA livre apos interrupcao anterior ao fechamento'
    fi
  fi
  echo "Evidencias: $report"
  echo "Porta de QA: $port"
  exit "$code"
}
trap cleanup EXIT

"$python" -B "$worktree/tests/e2e/seed.py" "$report/data/jobs" > "$report/seed.log"
qa_backend verify-free

export N3LX_STEM_RUNTIME_DIR="$(cygpath -w "$runtime")"
export N3LX_STEM_DATA_DIR="$(cygpath -w "$report/data")"
export N3LX_STEM_PROFILE_DIR="$(cygpath -w "$report/profile")"

cat <<'STEPS'

=== BATERIA UNICA (NA JANELA DO N3LX_STEM) ===
Use apenas E2E Fixture Track (6 segundos; tons sinteticos).

A. PLAY/PAUSE: escute, pause, retome, confira continuidade.
B. STOP: pare e reinicie; o som e o playhead devem reiniciar.
C. MUTE/SOLO: silencie e isole canais; escute a mudanca.
D. PAN ESTEREO: ajuste uma faixa para esquerda e direita, se tiver
   saida estereo disponivel.
E. DISPOSITIVO: se houver duas saidas, altere o dispositivo padrao
   do Windows e observe se audio continua ou exige reabertura.
F. QUALIDADE: escute cortes, estalos, distorcao ou atraso inesperado.

Nao precisa exportar de novo: WAV/FFprobe ja passaram no C35.1.
Ao terminar TODOS os testes, feche a janela normalmente.
Depois responda uma unica rodada de perguntas no Git Bash.

STEPS

"$python" -B - "$(cygpath -w "$exe")" "$port" <<'PY'
import os, subprocess, sys
exe, port = sys.argv[1:3]
proc = subprocess.Popen([exe, "--port=" + port],
                        cwd=os.path.dirname(exe),
                        env=os.environ.copy())
print("EXE iniciado com PID", proc.pid, "- aguardando fechamento normal.", flush=True)
try:
    code = proc.wait()
except KeyboardInterrupt:
    print("Bateria interrompida; feche a janela normalmente.", flush=True)
    raise SystemExit(130)
if code:
    raise SystemExit("EXE terminou com codigo " + str(code))
print("PASS: janela encerrada normalmente.", flush=True)
PY
gui_closed=1

echo
echo '=== C35.2 — REGISTRAR SUA ESCUTA (UMA VEZ) ==='
echo 'Digite s = funcionou, n = falhou, p = nao testado.'
ask() {
  local var="$1"
  local prompt="$2"
  local value
  while true; do
    printf '%s [s/n/p]: ' "$prompt"
    IFS= read -r value || return 1
    case "$value" in
      s|S|n|N|p|P)
        printf -v "$var" '%s' "$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
        return 0
        ;;
      *) echo 'Digite apenas s, n ou p.' ;;
    esac
  done
}
ask heard 'A. Som realmente audivel no dispositivo?'
ask transport 'B. Play, Pause, Retomar e Stop corretos?'
ask mute 'C. Mute/Solo alteraram o som corretamente?'
ask pan 'D. Pan esquerdo/direito correto?'
ask device 'E. Troca do dispositivo padrao funcionou?'
ask quality 'F. Sem estalos, cortes ou distorcao?'

"$python" -B - "$report/listening-qa.json" "$heard" "$transport" "$mute" "$pan" "$device" "$quality" <<'PY'
import json, sys
from pathlib import Path
keys = ("audibility", "transport", "mute_solo", "stereo_pan", "device_change", "sound_quality")
mapping = {"s": "PASS", "n": "FAIL", "p": "NOT_TESTED"}
results = dict(zip(keys, (mapping[x] for x in sys.argv[2:])))
required = ("audibility", "transport", "mute_solo", "sound_quality")
if "FAIL" in results.values():
    summary = "FAIL"
elif all(results[key] == "PASS" for key in keys):
    summary = "PASS"
elif all(results[key] == "PASS" for key in required):
    summary = "PARTIAL_OPTIONAL_NOT_TESTED"
else:
    summary = "PENDING_REQUIRED_CHECK"
Path(sys.argv[1]).write_text(json.dumps({
    "gate": "C35.2", "environment": "isolated synthetic Windows packaged EXE",
    "source": "human listening questionnaire; not automatic sound capture",
    "results": results, "summary": summary,
    "limits": ["no personal library", "no AMD inference proof"]
}, indent=2) + "\n", encoding="utf-8")
print("ACEITE AUDITIVO:", summary)
for key, value in results.items():
    print(" ", key, value)
sys.exit(1 if summary in ("FAIL", "PENDING_REQUIRED_CHECK") else 0)
PY
echo 'PASS: relatorio auditivo registrado (conferir status acima).'
