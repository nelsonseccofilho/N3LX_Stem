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
    if not shutil.which("uv"):
        return blocked(items,"browser-e2e","uv missing; no install attempted")
    modules = rt/"node_modules"
    cli = modules/"@playwright/test/cli.js"
    if not cli.is_file():
        return blocked(items,"browser-e2e","existing Playwright test runner missing")
    link = ROOT/"node_modules"
    created=False
    try:
        if not link.exists():
            try:
                link.symlink_to(modules,target_is_directory=True)
                created=True
            except OSError as e:
                return blocked(items,"browser-e2e","existing node_modules link unavailable: "+str(e))
        if not (link/"@playwright/test").is_dir():
            return blocked(items,"browser-e2e","incompatible worktree node_modules")
        port=subprocess.check_output(
            [node,str(ROOT/"scripts/qa/available-port.mjs")],
            text=True,timeout=20).strip()
        if not port.isdecimal() or not (1024<=int(port)<=65535) or port in ("8159","8162"):
            return blocked(items,"browser-e2e","unsafe QA port")
        e=dict(env)
        e.update({
            "STEMDECK_E2E_ISOLATED":"1","STEMDECK_E2E_PORT":port,
            "STEMDECK_E2E_DIR":str(report/"browser-scratch"),
            "STEMDECK_E2E_OUTPUT_DIR":str(report/"browser-results"),
            "N3LX_RELEASE_REPORT_DIR":str(report),
            "UV_NO_SYNC":"1","UV_OFFLINE":"1",
            "UV_PROJECT_ENVIRONMENT":str(rt/".venv"),
        })
        e.pop("CI",None)
        step(items,"browser-e2e",
            [node,str(cli),"test","-c","playwright.config.mjs","--reporter=list"],
            report,e)
    except (OSError,subprocess.SubprocessError) as err:
        blocked(items,"browser-e2e",str(err))
    finally:
        if created:
            if link.is_symlink() and link.resolve()==modules.resolve():
                link.unlink()
            else:
                raise RuntimeError("QA dependency link changed; refusing deletion")

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
    a=p.parse_args()
    rt=a.runtime.resolve()
    out=a.out_root.resolve()
    required=[rt/".venv/Scripts/python.exe",rt/".venv-directml/Scripts/python.exe",
              rt/"desktop-app/node_modules/electron/dist/electron.exe"]
    if not all(x.is_file() for x in required):
        raise SystemExit("BLOCKED: existing AMD runtime/DirectML/Electron missing")
    if not out.is_dir() or out.is_symlink() or any(
        within(out,x) or within(x,out) for x in (ROOT.resolve(),rt,rt/"data")):
        raise SystemExit("BLOCKED: report root must be separate from source and user data")
    if git("status","--porcelain"):
        raise SystemExit("BLOCKED: candidate worktree is not clean")
    node=shutil.which("node")
    if not node or not shutil.which("bash"):
        raise SystemExit("BLOCKED: node and Git Bash required")
    rev=git("rev-parse","HEAD")
    report=Path(tempfile.mkdtemp(prefix="ReleaseGate-",dir=out))
    env={k:v for k,v in os.environ.items() if not k.startswith(("STEMDECK_","N3LX_"))}
    env.update({"PYTHONDONTWRITEBYTECODE":"1","PYTHONIOENCODING":"utf-8"})
    python=str(required[0])
    items=[]
    print("Candidate:",rev,"\nPrivate report:",report,flush=True)
    try:
        step(items,"local-regressions",
            [python,"-B",str(ROOT/"scripts/verify-local-release.py"),
             "--python",python,"--node",node,"--report-dir",str(report/"local")],
            report,env,
            validator=lambda _:(None if json.loads(
                (report/"local/summary.json").read_text(encoding="utf-8")
            ).get("passed") is True else (_ for _ in ()).throw(
                RuntimeError("Local regression summary not PASS"))))
        browser(items,report,rt,env,node)
        pe=dict(env)
        pe.update({"N3LX_C34_RUNTIME":str(rt),"N3LX_C34_OUTPUTS":str(report)})
        step(items,"packaged-windows",
            ["bash",str(ROOT/"scripts/qa/c35-audio.sh")],report,pe,
            validator=lambda log:verify_package(report,rev,log))
        items.append({"step":"revision-stability",
            "status":"PASS" if git("rev-parse","HEAD")==rev else "FAIL",
            "detail":"Git HEAD unchanged check"})
    except KeyboardInterrupt:
        blocked(items,"interrupted","Never assume active QA backend stopped")
    finally:
        statuses=[x["status"] for x in items]
        overall=("FAIL" if "FAIL" in statuses else "BLOCKED" if "BLOCKED" in statuses
                 else "PASS" if statuses and all(x=="PASS" for x in statuses) else "INCOMPLETE")
        gaps={
            "real_amd_inference":"NOT_EXECUTED: no real GPU model test run here",
            "pt_en_real_sung_alignment":"NOT_EXECUTED: synthetic tones do not validate sung words",
            "clean_machine_installer":"NOT_EXECUTED: current EXE is an update package",
        }
        result={"revision":rev,"execution":"local Windows","hosted_ci":False,
            "private_library_used":False,"automation":overall,
            "release_ready":False,"steps":items,
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
    return 0 if overall=="PASS" else 1

if __name__=="__main__":
    raise SystemExit(main())
