from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import JOB_ID_RE, JOBS_DIR
from app.core.registry import get
from app.pipeline import guitar_detail

router = APIRouter(tags=["guitar-detail"])
_actions: dict[str, asyncio.Lock] = {}


def action_lock(job_id):
    return _actions.setdefault(job_id, asyncio.Lock())


def ready(job_id):
    job = get(job_id) if JOB_ID_RE.fullmatch(job_id) else None
    if not job:
        raise HTTPException(404, "Música não encontrada.")
    if (
        job.status != "done"
        or job.trashed_at
        or not (JOBS_DIR / job_id / "stems/guitar.wav").is_file()
    ):
        raise HTTPException(409, "Selecione uma música pronta com pista de guitarra.")
    return job, JOBS_DIR / job_id


class DetailRequest(BaseModel):
    roles: list[Literal["lead", "acoustic", "rhythm"]] = Field(
        default_factory=lambda: list(guitar_detail.ROLES), min_length=1, max_length=3
    )


@router.get("/{job_id}/guitar-detail")
def status(job_id: str):
    job, directory = ready(job_id)
    return guitar_detail.view(job.id, directory)


@router.post("/{job_id}/guitar-detail", status_code=202)
async def start(job_id: str, body: DetailRequest):
    job, directory = ready(job_id)
    if not guitar_detail.environment()[2]:
        raise HTTPException(503, "O ambiente local do SAM Audio não está instalado.")
    try:
        async with action_lock(job_id):
            guitar_detail.start(
                job, directory, [role for role in guitar_detail.ROLES if role in body.roles]
            )
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return guitar_detail.view(job_id, directory)


@router.post("/{job_id}/guitar-detail/cancel")
def cancel(job_id: str):
    job, directory = ready(job_id)
    guitar_detail.cancel(job.id)
    return guitar_detail.view(job.id, directory)


@router.post("/{job_id}/guitar-detail/{action}")
async def apply(job_id: str, action: Literal["apply", "original"]):
    job, directory = ready(job_id)
    try:
        async with action_lock(job_id):
            await asyncio.to_thread(
                guitar_detail.apply, job, directory, original=action == "original"
            )
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return guitar_detail.view(job_id, directory)
