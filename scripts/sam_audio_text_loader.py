"""Load official SAM text/audio modules in an isolated research worker.

No optional video encoders, automatic span predictors, or candidate rankers are
constructed. All weights required by text/audio inference must match exactly.
The upstream source tree and installed packages remain unchanged.
"""

from __future__ import annotations

import ast
import json
import sys
import types
from pathlib import Path


def _package(name: str, path: Path):
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module
    return module


def _source_module(name: str, path: Path, keep):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tree.body = [node for node in tree.body if keep(node)]
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(tree, str(path), "exec"), module.__dict__)
    return module


def load_upstream(source: Path):
    """Import real upstream classes while excluding unavailable optional imports."""
    root = source / "sam_audio"
    _package("sam_audio", root)
    _package("sam_audio.model", root / "model")

    def keep_config(node):
        if isinstance(node, ast.ImportFrom) and node.module in (
            "core.audio_visual_encoder.config",
            "transformers",
        ):
            return False
        return not (isinstance(node, ast.ClassDef) and node.name == "SAMAudioJudgeConfig")

    config = _source_module("sam_audio.model.config", root / "model/config.py", keep_config)

    def keep_processor(node):
        if isinstance(node, ast.ImportFrom) and node.module == "torchcodec.decoders":
            return False
        if isinstance(node, ast.ImportFrom) and node.module == "sam_audio.model.config":
            node.names = [alias for alias in node.names if alias.name == "SAMAudioConfig"]
        return not (isinstance(node, ast.ClassDef) and node.name == "SAMAudioJudgeProcessor")

    processor = _source_module("sam_audio.processor", root / "processor.py", keep_processor)

    def keep_model(node):
        return not (
            isinstance(node, ast.ImportFrom)
            and node.module
            in ("core.audio_visual_encoder", "sam_audio.model.vision_encoder", "sam_audio.ranking")
        )

    model = _source_module("sam_audio.model.model", root / "model/model.py", keep_model)
    return config, processor, model


def load_text_audio(source: Path, weights: Path, text_weights: Path):
    import torch
    import transformers

    config_module, processor_module, upstream = load_upstream(source)
    raw = json.loads((weights / "config.json").read_text(encoding="utf-8"))
    raw.update(visual_ranker=None, text_ranker=None, span_predictor=None)
    raw["text_encoder"]["name"] = str(text_weights)
    cfg = config_module.SAMAudioConfig(**raw)

    class TextAudioSAM(upstream.SAMAudio):
        def __init__(self):
            torch.nn.Module.__init__(self)
            self.audio_codec = upstream.DACVAE(cfg.audio_codec)
            self.text_encoder = upstream.T5TextEncoder(cfg.text_encoder)
            # Only the feature dimension is read for a text-only, zero-video input.
            # No substitute model produces any video features.
            self.vision_encoder = types.SimpleNamespace(dim=cfg.vision_encoder.dim)
            self.transformer = upstream.DiT(cfg.transformer)
            self.proj = torch.nn.Linear(cfg.in_channels, cfg.transformer.dim)
            self.align_masked_video = upstream.AlignModalities(
                cfg.vision_encoder.dim, cfg.transformer.dim
            )
            self.embed_anchors = upstream.EmbedAnchors(
                cfg.num_anchors, cfg.anchor_embedding_dim, cfg.transformer.dim
            )
            self.memory_proj = torch.nn.Linear(cfg.text_encoder.dim, cfg.transformer.dim)
            self.timestep_emb = upstream.SinusoidalEmbedding(cfg.transformer.dim)
            self.visual_ranker = self.text_ranker = None

    # T5 is loaded independently, as in upstream SAM. Restrict it to local files.
    # Its configuration is pinned and downloaded by the research setup command.
    model = TextAudioSAM().eval()
    checkpoint = torch.load(
        weights / "checkpoint.pt", map_location="cpu", weights_only=True, mmap=True
    )
    excluded_prefixes = ("vision_encoder.", "visual_ranker.", "text_ranker.", "span_predictor.")
    relevant = {k: v for k, v in checkpoint.items() if not k.startswith(excluded_prefixes)}
    loaded = torch.nn.Module.load_state_dict(model, relevant, strict=False, assign=True)
    missing = [k for k in loaded.missing_keys if not k.startswith("text_encoder.")]
    if missing or loaded.unexpected_keys:
        raise RuntimeError(f"Required SAM weights mismatch: {missing=}, {loaded.unexpected_keys=}")
    processor = processor_module.SAMAudioProcessor(
        audio_hop_length=model.audio_codec.hop_length,
        audio_sampling_rate=model.sample_rate,
    )
    receipt = {
        "checkpoint_loaded": True,
        "required_weights_match": True,
        "loaded_tensors": len(relevant),
        "excluded_optional_tensors": len(checkpoint) - len(relevant),
        "parameters": sum(p.numel() for p in model.parameters()),
        "transformers": transformers.__version__,
        "omitted": ["vision_encoder", "span_predictor", "visual_ranker", "text_ranker"],
    }
    return model, processor, receipt
