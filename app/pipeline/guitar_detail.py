"""Supervised local SAM tasks. Source stems and active mixes survive failures."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import ROOT

GUITAR_LABELS = {
    "guitar_lead": "Guitarra solo estimada",
    "guitar_acoustic": "Violão estimado",
    "guitar_rhythm": "Guitarra base estimada",
    "residual_guitar": "Outras guitarras / sobras",
}
ROLES = ("lead", "acoustic", "rhythm")


def environment():
    source = Path(os.environ.get("STEMDECK_SAM_SOURCE", ROOT.parent / "sam-audio-amd"))
    python = Path(
        os.environ.get(
            "STEMDECK_SAM_PYTHON",
            source / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"),
        )
    )
    required = [
        python,
        source / "sam_audio/model/model.py",
        source / "models/sam-audio-small/checkpoint.pt",
        source / "models/t5-base/model.safetensors",
    ]
    return source, python, all(path.is_file() for path in required)


def read_result(job_dir):
    try:
        value = json.loads((job_dir / "guitar-detail.json").read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("run_id"), str):
            return None
        if len(value["run_id"]) != 32 or any(c not in "0123456789abcdef" for c in value["run_id"]):
            return None
        return value
    except (OSError, ValueError, TypeError):
        return None


def atomic_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def run_automatic(job, stems):
    """Already inside the extraction lock: do not enqueue a second async task."""
    import soundfile as sf

    from app.core.worker_progress import run_progress_worker
    from app.pipeline.cancel import check_cancel

    check_cancel(job)
    source, python, available = environment()
    if not available:
        raise RuntimeError("O ambiente local do SAM Audio não está instalado.")
    run_id = uuid.uuid4().hex
    output = stems.parent / "guitar-details" / run_id
    result = run_progress_worker(
        job,
        [
            str(python),
            str(ROOT / "scripts/sam_audio_guitar_worker.py"),
            "--source",
            str(source),
            "--input",
            str(stems / "guitar.wav"),
            "--output",
            str(output),
            "--roles",
            *ROLES,
            "--pipeline-progress",
        ],
        max(1800, int((job.duration_sec or 0) * 25) + 600),
    )
    check_cancel(job)
    if result.returncode:
        raise RuntimeError("SAM Audio não concluiu o refinamento na GPU AMD.")
    receipt = json.loads((output / "result.json").read_text(encoding="utf-8"))
    if receipt.get("status") != "done" or set(receipt.get("names", [])) != set(GUITAR_LABELS):
        raise ValueError("SAM Audio produziu pistas incompletas.")
    with (stems / "guitar.wav").open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != receipt.get("input_sha256"):
            raise ValueError("A guitarra de referência mudou durante o refinamento.")
    reference = sf.info(stems / "guitar.wav")
    for name in receipt["names"]:
        info = sf.info(output / f"{name}.wav")
        if (info.frames, info.channels, info.samplerate) != (
            reference.frames,
            reference.channels,
            reference.samplerate,
        ):
            raise ValueError("O refinamento alterou o alinhamento das guitarras.")
    for name in receipt["names"]:
        check_cancel(job)
        temporary = stems / f".{name}.{run_id}.tmp"
        shutil.copyfile(output / f"{name}.wav", temporary)
        temporary.replace(stems / f"{name}.wav")
    receipt.update(run_id=run_id, applied=True, automatic=True)
    return receipt


@dataclass
class Run:
    job_id: str
    roles: list[str] = field(default_factory=list)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "queued"
    progress: dict = field(default_factory=dict)
    error: str | None = None
    cancel: bool = False
    process: object = None
    task: object = None
    started: float = field(default_factory=time.monotonic)
    finished: float | None = None


_runs: dict[str, Run] = {}


def view(job_id, job_dir):
    saved = read_result(job_dir)
    run = _runs.get(job_id)
    result = {
        "available": environment()[2],
        "status": "done" if saved else "idle",
        "result_available": saved is not None,
        "applied": bool(saved and saved.get("applied")),
        "roles": saved.get("roles", []) if saved else [],
        "estimate_notice": "Estimativas de guitarra; pode haver vazamentos. A original é preservada.",
    }
    if run:
        result.update(
            status=run.status,
            progress=run.progress,
            error=run.error,
            elapsed=(run.finished or time.monotonic()) - run.started,
            run_id=run.run_id,
        )
        if run.status in ("queued", "running", "cancelling"):
            result["roles"] = run.roles
    if saved:
        result["result"] = {
            k: saved.get(k)
            for k in (
                "names",
                "sample_rate",
                "samples",
                "channels",
                "adapter",
                "elapsed",
                "reconstruction_max_abs_error",
                "sequential_partition",
            )
        }
    return result


def start(job, job_dir, roles):
    old = _runs.get(job.id)
    if old and old.status in ("queued", "running", "cancelling"):
        raise ValueError("Já existe um detalhamento em andamento para esta música.")
    saved = read_result(job_dir)
    if saved and saved.get("applied"):
        raise ValueError("Volte às guitarras originais antes de gerar outro detalhamento.")
    run = Run(job.id, roles=list(roles))
    _runs[job.id] = run
    run.task = asyncio.create_task(_execute(run, job, job_dir, roles))
    return run


async def stop(run):
    proc = run.process
    if proc and proc.returncode is None:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(proc.wait(), 5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()


def cancel(job_id):
    run = _runs.get(job_id)
    if run and run.status in ("queued", "running", "cancelling"):
        run.cancel = True
        run.status = "cancelling"
        # A queued task cannot report cancelled until its waiting coroutine ends.
        if run.process is None and run.task:
            run.task.cancel()
            run.status = "cancelled"
            run.finished = time.monotonic()
    return run


async def _execute(run, job, job_dir, roles):
    from app.core.registry import get
    from app.pipeline.runner import _pipeline_lock

    output = job_dir / "guitar-details" / run.run_id
    tail = []
    try:
        async with _pipeline_lock:
            if run.cancel:
                run.status = "cancelled"
                return
            if (
                get(job.id) is not job
                or job.trashed_at
                or not (job_dir / "stems/guitar.wav").is_file()
            ):
                raise RuntimeError("A música não está mais disponível para detalhamento.")
            source, python, available = environment()
            if not available:
                raise RuntimeError("O ambiente local do SAM Audio não está instalado.")
            from app.pipeline.separate import _kill_worker

            _kill_worker()
            run.status = "running"
            env = {
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
                "STEMDECK_PARENT_PID": str(os.getpid()),
            }
            run.process = await asyncio.create_subprocess_exec(
                str(python),
                str(ROOT / "scripts/sam_audio_guitar_worker.py"),
                "--source",
                str(source),
                "--input",
                str(job_dir / "stems/guitar.wav"),
                "--output",
                str(output),
                "--roles",
                *roles,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
                cwd=ROOT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            last_message = time.monotonic()
            while True:
                if run.cancel or get(job.id) is not job or job.trashed_at:
                    run.cancel = True
                    await stop(run)
                    break
                try:
                    line = await asyncio.wait_for(run.process.stdout.readline(), 1)
                except asyncio.TimeoutError:
                    if time.monotonic() - last_message > 600:
                        raise RuntimeError(
                            "O SAM ficou sem progresso por mais de dez minutos."
                        ) from None
                    continue
                if not line:
                    break
                last_message = time.monotonic()
                text = line.decode("utf-8", errors="replace").strip()
                if text.startswith("@@GUITAR@@"):
                    run.progress = json.loads(text[len("@@GUITAR@@") :])
                    run.progress.pop("result", None)
                elif text:
                    tail = [*tail[-7:], text[:1000]]
            code = await run.process.wait()
            if run.cancel:
                run.status = "cancelled"
                return
            if code:
                raise RuntimeError(
                    "Não foi possível detalhar as guitarras na AMD. "
                    + (
                        "Memória de vídeo insuficiente."
                        if any("memory" in line.lower() for line in tail)
                        else "Os arquivos originais foram preservados."
                    )
                )
            receipt = json.loads((output / "result.json").read_text(encoding="utf-8"))
            if get(job.id) is not job or job.trashed_at or receipt.get("status") != "done":
                raise RuntimeError("A música não está disponível ou o resultado não foi concluído.")
            if set(receipt.get("names", [])) - GUITAR_LABELS.keys():
                raise RuntimeError("O SAM produziu nomes de pistas inesperados.")
            previous = read_result(job_dir)
            if previous and previous.get("applied"):
                receipt["previous_layout"] = previous.get("previous_layout")
            receipt.update(run_id=run.run_id, applied=False)
            atomic_json(job_dir / "guitar-detail.json", receipt)
            run.status = "done"
    except asyncio.CancelledError:
        run.cancel = True
        run.status = "cancelled"
    except Exception as error:
        run.status, run.error = "error", str(error)
    finally:
        await stop(run)
        run.process = None
        run.finished = time.monotonic()


def apply(job, job_dir, *, original=False):
    from app.core.registry import persist
    from app.core.studio import DRUM_STEMS, read_layout
    from app.pipeline.collect import merge_stem_peaks

    receipt = read_result(job_dir)
    if not receipt:
        raise ValueError("Esta música ainda não tem um detalhamento concluído.")
    run = _runs.get(job.id)
    if run and run.status in ("queued", "running", "cancelling"):
        raise ValueError("Aguarde o detalhamento terminar antes de trocar as pistas.")
    layout_path = job_dir / "studio.json"
    stems = job_dir / "stems"
    if original:
        if receipt.get("applied"):
            previous = receipt.get("previous_layout")
            if previous is None:
                layout_path.unlink(missing_ok=True)
            else:
                atomic_json(layout_path, previous)
            job.stems = [stem for stem in job.stems if stem["name"] not in GUITAR_LABELS]
            # These are published copies; canonical outputs remain in guitar-details.
            # Removing the copies also prevents registry orphan recovery after restart.
            for name in GUITAR_LABELS:
                (stems / f"{name}.wav").unlink(missing_ok=True)
            receipt["applied"] = False
    else:
        if receipt.get("applied"):
            return
        with (stems / "guitar.wav").open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != receipt["input_sha256"]:
                raise ValueError(
                    "A guitarra original mudou. Gere novas estimativas antes de aplicar."
                )
        output = job_dir / "guitar-details" / receipt["run_id"]
        names = receipt["names"]
        if not names or any(
            name not in GUITAR_LABELS or not (output / f"{name}.wav").is_file() for name in names
        ):
            raise ValueError("Os arquivos do detalhamento não estão completos.")
        previous = (
            json.loads(layout_path.read_text(encoding="utf-8")) if layout_path.exists() else None
        )
        receipt["previous_layout"] = previous
        layout = read_layout(job_dir) or {"labels": {}, "active_names": [], "profile": "complete"}
        active = layout["active_names"] or [
            s["name"]
            for s in job.stems
            if s["name"] not in GUITAR_LABELS and s["name"] != "original"
        ]
        if all(name in active for name in ("lead_vocals", "backing_vocals")):
            active = [name for name in active if name != "vocals"]
        if all(name in active for name in DRUM_STEMS):
            active = [name for name in active if name != "drums"]
        for name in names:
            temporary = stems / f".{name}.{receipt['run_id']}.tmp"
            shutil.copyfile(output / f"{name}.wav", temporary)
            temporary.replace(stems / f"{name}.wav")
        merge_stem_peaks(stems, names)
        layout.update(
            profile="complete",
            labels={**layout["labels"], **GUITAR_LABELS},
            active_names=[name for name in active if name != "guitar"] + names,
            notice="Guitarras estimadas pelo SAM Audio. Outras guitarras e sobras foram preservadas.",
        )
        atomic_json(layout_path, layout)
        job.stems = [stem for stem in job.stems if stem["name"] not in GUITAR_LABELS] + [
            {"name": name, "url": f"/api/jobs/{job.id}/stems/{name}.wav?v={receipt['run_id']}"}
            for name in names
        ]
        receipt["applied"] = True
    atomic_json(job_dir / "guitar-detail.json", receipt)
    persist(job_dir.parent)


async def shutdown():
    runs = list(_runs.values())
    for run in runs:
        run.cancel = True
        if run.task and not run.task.done():
            run.task.cancel()
    await asyncio.gather(*(run.task for run in runs if run.task), return_exceptions=True)
    _runs.clear()
