"""Build a Windows update using a previously installed, pinned Electron runtime.

The ZIP contains the desktop executable and app sources. Python environments,
AMD workers, model weights and private data stay in the selected installation.
Never pass an existing output directory: builds are append-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path


def build(source: Path, installation: Path, output: Path) -> Path:
    source, installation, output = source.resolve(), installation.resolve(), output.resolve()
    if output.exists():
        raise ValueError("output directory already exists; use a fresh destination")
    version = json.loads((source / "desktop-app/package.json").read_text())["version"]
    electron = installation / "desktop-app/node_modules/electron/dist"
    if not (electron / "electron.exe").is_file():
        raise ValueError("installed Electron distribution is missing")
    installed_version = (electron / "version").read_text().strip()
    pinned = json.loads((source / "desktop-app/package.json").read_text())["devDependencies"]["electron"]
    if installed_version != pinned:
        raise ValueError(f"Electron version {installed_version} differs from pin {pinned}")
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if subprocess.run(["git", "-C", str(source), "diff", "--quiet", "HEAD"]).returncode:
        raise ValueError("commit reviewed changes before building")
    output.mkdir(parents=True)
    package = output / f"N3LX_Stem-Windows-Update-{version}"
    shutil.copytree(electron, package)
    (package / "electron.exe").rename(package / "N3LX_Stem.exe")
    default = package / "resources/default_app.asar"
    if default.exists():
        default.unlink()
    shell = package / "resources/app"
    shell.mkdir()
    for name in ("main.cjs", "package.json"):
        shutil.copy2(source / "desktop-app" / name, shell / name)
    backend = package / "resources/stemdeck"
    files = subprocess.check_output(["git", "-C", str(source), "ls-files", "-z"], text=True).split("\0")
    for rel in files:
        if not rel or not (rel.startswith(("app/", "static/", "scripts/", "desktop/src-tauri/icons/")) or rel in ("pyproject.toml", "uv.lock", "LICENSE")):
            continue
        target = backend / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, target)
    (backend / "static/version.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    metadata = {"product": "N3LX_Stem", "version": version, "source_revision": revision,
                "electron": installed_version, "kind": "update-requires-existing-amd-installation",
                "includes_python_models_or_user_data": False}
    (package / "build-info.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (package / "LEIA-ME.txt").write_text(
        "N3LX_Stem - atualizacao Windows\n\nExtraia todo este ZIP e abra N3LX_Stem.exe. "
        "Mantenha a pasta resources e os demais arquivos juntos.\n"
        "Requer a instalacao AMD existente com .venv e .venv-directml. Selecione essa pasta na primeira abertura.\n"
        "Feche a outra instancia e seu servidor antes de usar a mesma biblioteca.\n"
        "O pacote usa a biblioteca data da instalacao escolhida, sem copia-la ou substitui-la. "
        "Os ambientes Python, pesos e ferramentas especializadas nao estao incluidos.\n"
        "A versao candidata passou por QA com audio sintetico; nova separacao musical completa e GPU Vulkan "
        "nao foram medidas nesta revisao.\n", encoding="utf-8")
    hashes = {}
    for file in sorted(package.rglob("*")):
        if file.is_file():
            hashes[file.relative_to(package).as_posix()] = hashlib.file_digest(file.open("rb"), "sha256").hexdigest()
    manifest = package / "sha256-manifest.json"
    manifest.write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    archive = output / (package.name + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6, strict_timestamps=False) as z:
        for file in sorted(package.rglob("*")):
            if file.is_file():
                z.write(file, file.relative_to(output))
    digest = hashlib.file_digest(archive.open("rb"), "sha256").hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError("ZIP integrity verification failed")
    print(json.dumps({**metadata, "archive": str(archive), "sha256": digest,
                      "exe": str(package / "N3LX_Stem.exe"), "files": len(hashes)}, indent=2))
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    build(options.source, options.installation, options.output)

