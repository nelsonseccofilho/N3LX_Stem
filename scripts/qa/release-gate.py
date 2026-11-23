"""One-shot release validation for isolated Windows QA worktrees."""
from __future__ import annotations
import argparse, datetime as dt, json, os, shutil, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIO_ACCEPTANCE_SHA = "f7e9330785ddecc5968c890977bc9d3d95f464e3"

def git(*a):
    return subprocess.check_output(["git","-C",str(ROOT),*a],text=True).strip()

def within(p, parent):
    return p == parent or parent in p.parents

def validate_output_root(raw_output, source_root, runtime_root):
    """Allow a QA worktree *inside* the reports parent, never reports inside source.

    Typical safe layout:
        N3LX_Stem-Releases/
            release-gate-qa/     (separate Git worktree)
            ReleaseGate-XXXXXXXX/ (new sibling, created with mkdtemp)
    """
    if raw_output.is_symlink():
        raise ValueError("BLOCKED: report root must not be a symlink")
    output = raw_output.resolve()
    source = source_root.resolve()
    runtime = runtime_root.resolve()
    if not output.is_dir():
        raise ValueError("BLOCKED: report root does not exist")
    if within(output, source):
        raise ValueError("BLOCKED: report root is inside the QA worktree")
    if within(output, runtime) or within(runtime, output):
        raise ValueError("BLOCKED: report root overlaps the personal runtime")
    return output


def bash_path(path):
    return subprocess.check_output(
        ["cygpath", "-u", str(path)], text=True).strip()


def step(items, name, cmd, report, env, validator=None):
    print("\n== " + name + " ==",flush=True)
    log = report / (name + ".log")
    try:
        with log.open("w",encoding="utf-8") as f:
            proc = subprocess.Popen(cmd,cwd=ROOT,env=env,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                text=True,encoding="utf-8",errors="replace")
            for line in proc.stdout:
                print(line,end="",flush=True)
                f.write(line)
                f.flush()
            code = proc.wait()
        if code:
            raise RuntimeError("Exit "+str(code))
        if validator:
            validator(log)
        status,detail="PASS",str(log)
    except (RuntimeError,OSError,ValueError,AssertionError) as e:
        status,detail="FAIL",str(e)
    items.append({"step":name,"status":status,"detail":detail})
    print(name+": "+status+" "+detail,flush=True)

def blocked(items,name,reason):
    items.append({"step":name,"status":"BLOCKED","detail":reason})
    print(name+": BLOCKED "+reason,flush=True)

def browser(items,report,rt,env,node):
    # C34/C35 already validate this installed Python + uvicorn. The isolated
    # E2E backend does not need the uv command or package resolution.
    if not (rt/".venv/Scripts/python.exe").is_file():
        return blocked(items,"browser-e2e","Existing runtime Python missing")
    modules = rt/"node_modules"
    cli = modules/"@playwright/test/cli.js"
    if not cli.is_file():
        return blocked(items,"browser-e2e","existing Playwright test runner missing")
    # Resolve Playwright through the installed runtime via the ESM loader.
    # A Windows Git Bash user might not have permission to create symlinks.
    loader=ROOT/"scripts/qa/e2e-runtime-loader.mjs"
    browser_preflight=ROOT/"scripts/qa/browser-preflight.mjs"
    if not loader.is_file() or not browser_preflight.is_file():
        return blocked(items,"browser-e2e","QA loader or browser preflight missing")
    try:
        port=subprocess.check_output(
            [node,str(ROOT/"scripts/qa/available-port.mjs")],
            text=True,timeout=20).strip()
        if not port.isdecimal() or not (1024<=int(port)<=65535) or port in ("8159","8162"):
            return blocked(items,"browser-e2e","unsafe QA port")
        e=dict(env)
        e.update({
            "STEMDECK_E2E_ISOLATED":"1","STEMDECK_E2E_PORT":port,
            "STEMDECK_E2E_DIR":bash_path(report/"browser-scratch"),
            "STEMDECK_E2E_OUTPUT_DIR":str(report/"browser-results"),
            "N3LX_RELEASE_REPORT_DIR":bash_path(report),
            "N3LX_RELEASE_PYTHON":bash_path(rt/".venv/Scripts/python.exe"),
            "N3LX_RELEASE_TEST_RUNTIME":str(rt),
            # Playwright also loads TS/JS configs through CJS transforms.
            "NODE_PATH":str(modules),
        })
        e.pop("CI",None)
        # On Windows Node 26 the loader argument must be a file:// URI.
        # A raw C:\\... path is parsed as an unsupported "c:" URL scheme.
        loader_uri=loader.resolve().as_uri()
        preflight=subprocess.run(
            [node,"--experimental-loader",loader_uri,
             "--input-type=module","-e",
             "import('@playwright/test').then(m => { if (!m.test || !m.expect) process.exitCode = 3; })"],
            cwd=ROOT,env=e,capture_output=True,text=True,timeout=30)
        if preflight.returncode:
            detail=(preflight.stderr or preflight.stdout).strip()
            return blocked(items,"browser-e2e",
                "Playwright loader preflight failed; server not started: "+detail[-1000:])
        print("PASS: Node ESM loader and Playwright import (no server started)",flush=True)
        # The previous 330 one-millisecond failures were caused by absent
        # Chromium. Launch a browser once before the test workers start.
        # Only existing local browsers are considered, without installing any.
        browser_check=subprocess.run(
            [node,str(browser_preflight)],cwd=ROOT,env=e,
            capture_output=True,text=True,timeout=70)
        if browser_check.returncode:
            (report/"browser-preflight.log").write_text(
                browser_check.stdout+browser_check.stderr,encoding="utf-8")
            return blocked(items,"browser-e2e",
                "No launchable local browser; server not started. See browser-preflight.log")
        browser_info=json.loads(browser_check.stdout.strip())
        if browser_info.get("status")!="PASS" or browser_info.get("channel") not in (None,"msedge","chrome"):
            return blocked(items,"browser-e2e","Invalid browser preflight result")
        (report/"browser-preflight.json").write_text(
            json.dumps(browser_info,indent=2)+"\n",encoding="utf-8")
        e["N3LX_E2E_BROWSER_CHANNEL"]=browser_info.get("channel") or ""
        print("PASS: browser launch preflight: "+browser_info["browser"],flush=True)
        step(items,"browser-e2e",
            [node,"--experimental-loader",loader_uri,str(cli),
             "test","-c","playwright.config.mjs","--reporter=list",
             "--max-failures=1"],
            report,e)
    except (OSError,subprocess.SubprocessError) as err:
        blocked(items,"browser-e2e",str(err))
def verify_local(report):
    result = json.loads((report/"local/summary.json").read_text(encoding="utf-8"))
    if result.get("passed") is not True:
        raise RuntimeError("Local regression summary not PASS")

def verify_package(report,rev,log):
    folders=list(report.glob("C35-Audio-*"))
    if len(folders)!=1:
        raise RuntimeError("Expected one isolated packaged QA")
    result=json.loads((folders[0]/"audio-qa.json").read_text(encoding="utf-8"))
    if result.get("passed") is not True or result.get("revision")!=rev:
        raise RuntimeError("Packaged WAV/UI QA failed for candidate revision")
    output=log.read_text(encoding="utf-8")
    if "BLOCKED:" in output or not any(x in output for x in (
        "PASS: QA port verified free after packaged close",
        "PASS: QA port released during controller status check",
        "PASS: packaged QA backend stopped cooperatively; port released")):
        raise RuntimeError("Safe QA backend teardown not verified")


# Only runner and test-only files may vary when carrying prior PASS evidence.
# In particular, never carry results across a change to app, desktop,
# static, runtime settings, dependencies or release packaging.
RESUMABLE_QA_FILES = frozenset({
    "scripts/qa/release-gate.py",
    "scripts/qa/release-gate.sh",
    "scripts/qa/e2e-runtime-loader.mjs",
    "scripts/qa/browser-preflight.mjs",
    "playwright.config.mjs",
    "tests/e2e/serve.sh",
    "tests/qa/test_release_output_paths.py",
    "docs/RELEASE_GATE_ONE_SHOT.md",
})

def resume_evidence(directory, candidate, outputs):
    """Verify a private previous gate run; never rename, copy or modify it."""
    if directory.is_symlink():
        raise RuntimeError("Resume report is a symlink")
    prior = directory.resolve()
    if not prior.is_dir() or prior.parent != outputs or not prior.name.startswith("ReleaseGate-"):
        raise RuntimeError("Resume report is not an isolated previous ReleaseGate folder")
    summary_file = prior/"summary.json"
    if not summary_file.is_file():
        raise RuntimeError("Previous release summary is missing")
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    old = summary.get("revision")
    if not isinstance(old,str) or len(old)!=40 or not all(c in "0123456789abcdef" for c in old):
        raise RuntimeError("Previous revision must be a full Git commit hash")
    if summary.get("hosted_ci") is not False or summary.get("private_library_used") is not False:
        raise RuntimeError("Previous evidence lacks required isolation provenance")
    ancestor = subprocess.run(
        ["git","-C",str(ROOT),"merge-base","--is-ancestor",old,candidate],
        capture_output=True)
    if ancestor.returncode:
        raise RuntimeError("Previous QA revision is not an ancestor of this candidate")
    changed = git("diff","--name-only",old,candidate).splitlines()
    unsafe = [name for name in changed if name not in RESUMABLE_QA_FILES]
    if unsafe:
        raise RuntimeError("Production/other files changed; full gate required: "+", ".join(unsafe))
    statuses = {x.get("step"):x.get("status") for x in summary.get("steps",[])}
    if statuses.get("local-regressions")!="PASS" or statuses.get("packaged-windows")!="PASS":
        raise RuntimeError("Previous gate lacks PASS in both reusable stages")
    verify_local(prior)
    verify_package(prior,old,prior/"packaged-windows.log")
    return {"report":str(prior),"revision":old,
            "carried_stages":["local-regressions","packaged-windows"],
            "changed_qa_files":changed}

def listening(rev):
    evidence={"status":"REVIEW_REQUIRED","source":"C35-ListeningBatch-X0UPCo0a"}
    if subprocess.run(["git","-C",str(ROOT),"merge-base","--is-ancestor",
                       AUDIO_ACCEPTANCE_SHA,rev],capture_output=True).returncode==0:
        diff=subprocess.check_output(
            ["git","-C",str(ROOT),"diff","--name-only",AUDIO_ACCEPTANCE_SHA,rev,
             "--","app","static","desktop-app","desktop","packaging"],text=True).strip()
        if not diff:
            evidence["status"]="PRIOR_HUMAN_PASS_CARRIED"
            evidence["note"]="Product code unchanged; not a new physical listening test"
        else:
            evidence["changed_product_files"]=diff.splitlines()[:50]
    return evidence

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runtime",type=Path,required=True)
    p.add_argument("--out-root",type=Path,required=True)
    p.add_argument("--resume-from",type=Path,default=None,
                   help="Re-use already-PASS local and packaged QA from an earlier SHA when only the gate machinery changed")
    a=p.parse_args()
    rt=a.runtime.resolve()
    required=[rt/".venv/Scripts/python.exe",rt/".venv-directml/Scripts/python.exe",
              rt/"desktop-app/node_modules/electron/dist/electron.exe"]
    if not all(x.is_file() for x in required):
        raise SystemExit("BLOCKED: existing AMD runtime/DirectML/Electron missing")
    try:
        out=validate_output_root(a.out_root,ROOT,rt)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if git("status","--porcelain"):
        raise SystemExit("BLOCKED: candidate worktree is not clean")
    node=shutil.which("node")
    if not node or not shutil.which("bash"):
        raise SystemExit("BLOCKED: node and Git Bash required")
    rev=git("rev-parse","HEAD")
    try:
        carry=resume_evidence(a.resume_from,rev,out) if a.resume_from else None
    except (RuntimeError,ValueError,OSError,json.JSONDecodeError) as exc:
        raise SystemExit("BLOCKED: invalid resume evidence: "+str(exc)) from exc
    report=Path(tempfile.mkdtemp(prefix="ReleaseGate-",dir=out))
    env={k:v for k,v in os.environ.items() if not k.startswith(("STEMDECK_","N3LX_"))}
    env.update({"PYTHONDONTWRITEBYTECODE":"1","PYTHONIOENCODING":"utf-8"})
    python=str(required[0])
    items=[]
    print("Candidate:",rev,"\nPrivate report:",report,flush=True)
    try:
        if carry:
            items.append({"step":"local-regressions","status":"CARRIED",
                          "detail":"Previously PASS at "+carry["revision"]+" (source "+carry["report"]+")"})
            print("local-regressions: CARRIED — validated evidence, not rerun",flush=True)
        else:
            step(items,"local-regressions",
                [python,"-B",str(ROOT/"scripts/verify-local-release.py"),
                 "--python",python,"--node",node,"--report-dir",str(report/"local")],
                report,env,validator=lambda _: verify_local(report))
        browser(items,report,rt,env,node)
        if carry:
            items.append({"step":"packaged-windows","status":"CARRIED",
                          "detail":"Previously PASS at "+carry["revision"]+" (source "+carry["report"]+")"})
            print("packaged-windows: CARRIED — validated evidence, not rerun",flush=True)
        else:
            pe=dict(env)
            pe.update({"N3LX_C34_RUNTIME":bash_path(rt),
                       "N3LX_C34_OUTPUTS":bash_path(report)})
            step(items,"packaged-windows",
                ["bash",bash_path(ROOT/"scripts/qa/c35-audio.sh")],report,pe,
                validator=lambda log:verify_package(report,rev,log))
        items.append({"step":"revision-stability",
            "status":"PASS" if git("rev-parse","HEAD")==rev else "FAIL",
            "detail":"Git HEAD unchanged check"})
    except KeyboardInterrupt:
        blocked(items,"interrupted","Never assume active QA backend stopped")
    finally:
        statuses=[x["status"] for x in items]
        overall=("FAIL" if "FAIL" in statuses else "BLOCKED" if "BLOCKED" in statuses
                 else "PASS_WITH_CARRIED_EVIDENCE" if statuses and "CARRIED" in statuses
                      and all(x in ("PASS","CARRIED") for x in statuses)
                 else "PASS" if statuses and all(x=="PASS" for x in statuses) else "INCOMPLETE")
        gaps={
            "real_amd_inference":"NOT_EXECUTED: no real GPU model test run here",
            "pt_en_real_sung_alignment":"NOT_EXECUTED: synthetic tones do not validate sung words",
            "clean_machine_installer":"NOT_EXECUTED: current EXE is an update package",
        }
        result={"revision":rev,"execution":"local Windows","hosted_ci":False,
            "private_library_used":False,"automation":overall,
            "release_ready":False,"steps":items,
            "resumed_evidence":carry,
            "human_listening":listening(rev),"release_gaps":gaps,
            "completed_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
        (report/"summary.json").write_text(
            json.dumps(result,indent=2)+"\n",encoding="utf-8")
        lines=["# Release candidate one-shot gate","",
            "Revision: "+rev,"Automation: "+overall,
            "RELEASE READY: NO (real AMD, real sung voice and installer unproven)","",
            "## Steps"]
        lines += ["- "+x["step"]+": "+x["status"]+" "+x["detail"] for x in items]
        lines += ["","## Remaining independent gaps"]
        lines += ["- "+k+": "+v for k,v in gaps.items()]
        lines += ["","Previous listening: "+result["human_listening"]["status"],
            "CI skipped never counts as passed. Logs are private."]
        (report/"RESULT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
        print("\nAUTOMATION:",overall,"\nRELEASE READY: NO","\nReport:",report)
    return 0 if overall in ("PASS","PASS_WITH_CARRIED_EVIDENCE") else 1

if __name__=="__main__":
    raise SystemExit(main())
