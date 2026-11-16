"""Persistent, text/audio-only SAM session for the isolated AMD worker."""

from __future__ import annotations

import gc
import os
from pathlib import Path


class SAMSession:
    def __init__(self, source: Path, adapter="RX 6600M"):
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch
        import torch_directml
        from sam_audio_amd_compat import configure_codec, configure_transformer
        from sam_audio_text_loader import load_text_audio

        torch.set_num_threads(4)
        index = next(
            i
            for i in range(torch_directml.device_count())
            if adapter.casefold() in torch_directml.device_name(i).casefold()
        )
        self.device = torch_directml.device(index)
        self.adapter = torch_directml.device_name(index).rstrip("\0")
        self.model, self.processor, self.receipt = load_text_audio(
            source, source / "models/sam-audio-small", source / "models/t5-base"
        )
        configure_codec(self.model.audio_codec)
        configure_transformer(self.model.transformer)
        self.text_cache = {}
        self.forward_names = (
            "transformer",
            "proj",
            "align_masked_video",
            "embed_anchors",
            "memory_proj",
            "timestep_emb",
        )

    def infer(self, audio, prompt, *, seed=42, progress=lambda **_: None):
        import torch
        from sam_audio_amd_compat import directml_t5_compat
        from torchdiffeq import odeint

        model, device = self.model, self.device
        batch = self.processor(
            audios=[torch.as_tensor(audio, dtype=torch.float32).reshape(1, -1)],
            descriptions=[prompt],
        )
        try:
            with torch.no_grad():
                if prompt not in self.text_cache:
                    progress(phase="text")
                    model.text_encoder.to(device)
                    with directml_t5_compat():
                        text, mask = model.text_encoder([prompt])
                    self.text_cache[prompt] = (text.cpu(), mask.cpu())
                    del text, mask
                    model.text_encoder.to("cpu")
                text, mask = self.text_cache[prompt]
                progress(phase="encode")
                model.audio_codec.to(device)
                features = model._get_audio_features(batch.audios.to(device)).cpu()
                model.audio_codec.to("cpu")
                for name in self.forward_names:
                    getattr(model, name).to(device)
                arguments = {
                    "audio_features": features.to(device),
                    "text_features": text.to(device),
                    "text_mask": mask.to(device),
                    "masked_video_features": torch.zeros(
                        1, model.vision_encoder.dim, features.shape[1], device=device
                    ),
                    "anchor_ids": batch.anchor_ids.to(device),
                    "anchor_alignment": batch.anchor_alignment.to(device),
                    "audio_pad_mask": batch.audio_pad_mask.to(device),
                }
                generator = torch.Generator().manual_seed(seed)
                noise = torch.randn(features.shape, generator=generator).to(device)
                evaluations = 0

                def field(t, value):
                    nonlocal evaluations
                    result = model(noisy_audio=value, time=t.expand(value.shape[0]), **arguments)
                    evaluations += 1
                    progress(phase="generate", evaluation=evaluations, evaluations=32)
                    return result

                states = odeint(
                    field,
                    noise,
                    torch.tensor([0.0, 1.0], device=device),
                    method="midpoint",
                    options={"step_size": 2 / 32},
                )
                latents = states[-1].transpose(1, 2).cpu()
                latents = latents.reshape(2, latents.shape[1] // 2, latents.shape[-1])
                del states, noise
                arguments.clear()
                for name in self.forward_names:
                    getattr(model, name).to("cpu")
                gc.collect()
                model.audio_codec.to(device)
                outputs = []
                # Preserve the complete time axis, but decode batch members serially.
                for index in range(2):
                    progress(phase="decode", output=index + 1, outputs=2)
                    value = latents[index : index + 1].to(device)
                    embedded = model.audio_codec.quantizer.out_proj(value)
                    # Fixed watermark message avoids discontinuities between windows.
                    message = torch.zeros(1, 16, device=device)
                    decoded = model.audio_codec.decoder(embedded, message=message).cpu()
                    outputs.append(decoded.flatten()[: len(audio)].numpy().copy())
                    del decoded, value, embedded
                    gc.collect()
                if any(len(value) != len(audio) for value in outputs):
                    raise RuntimeError("SAM output length does not match the audio window")
                return outputs
        finally:
            for name in (*self.forward_names, "audio_codec", "text_encoder"):
                getattr(model, name).to("cpu")
            gc.collect()
