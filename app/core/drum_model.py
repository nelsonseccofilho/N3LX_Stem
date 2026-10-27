"""Load the installed, trained DrumSep architecture without a second ML stack."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

MODEL = "MDX23C-DrumSep-aufr33-jarredou.ckpt"
PIECES = ("kick", "snare", "toms", "hh", "ride", "crash")


def _namespace(value):
    return (
        SimpleNamespace(**{k: _namespace(v) for k, v in value.items()})
        if isinstance(value, dict)
        else value
    )


def load_model(directory: Path, code: Path, device):
    import torch
    import yaml

    class Loader(yaml.SafeLoader):
        pass

    # The installed inference YAML has one training-only tuple; no Python objects execute.
    Loader.add_constructor(
        "tag:yaml.org,2002:python/tuple", lambda loader, node: loader.construct_sequence(node)
    )
    config = _namespace(
        yaml.load((directory / "config_drumsep_mdx23c.yaml").read_text(), Loader=Loader)
    )
    if tuple(config.training.instruments) != PIECES:
        raise ValueError("Unexpected DrumSep instrument order")
    spec = importlib.util.spec_from_file_location("stemdeck_drum_architecture", code)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = module.TFC_TDF_net(config, device=device)
    model.load_state_dict(
        torch.load(directory / MODEL, map_location="cpu", weights_only=True), strict=True
    )
    return model.eval().to(device), config
