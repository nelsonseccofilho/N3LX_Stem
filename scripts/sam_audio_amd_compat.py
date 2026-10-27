"""Local SAM compatibility helpers; no changes to upstream or installed Torch."""

from __future__ import annotations

import types
from contextlib import contextmanager


def real_rotary_forward(self, x, bhle=False, **_kwargs):
    """Equivalent RoPE using 4-D real tensors instead of 6-D broadcasting.

    DirectML's tensor descriptor aborts the process on the upstream broadcast.
    All arithmetic here stays on x.device; no host/CPU fallback is introduced.
    """
    import torch

    if bhle:
        x = x.transpose(1, 2)
    even = x[..., 0::2].float().contiguous()
    odd = x[..., 1::2].float().contiguous()
    freqs = self.freqs_cis[0, : x.shape[1], 0]
    cos = freqs[..., 0, 0].reshape(1, x.shape[1], 1, -1).expand_as(even).contiguous()
    sin = freqs[..., 1, 0].reshape(1, x.shape[1], 1, -1).expand_as(even).contiguous()
    result = torch.stack((even * cos - odd * sin, even * sin + odd * cos), dim=-1)
    result = result.flatten(-2).to(dtype=x.dtype)
    return result.transpose(1, 2) if bhle else result


def configure_transformer(model):
    """Patch only this worker's model instances, preserving learned weights."""
    rope = model.rope_embeddings
    if rope is not None:
        rope.forward = types.MethodType(real_rotary_forward, rope)
    configure_pointwise_convs(model)
    return model


def tensor_bound_clamp(x, minimum=None, maximum=None):
    """T5's representable scalar limits using GPU minimum/maximum kernels."""
    import torch

    if minimum is not None:
        bound = torch.as_tensor(minimum, device=x.device, dtype=x.dtype)
        x = torch.maximum(x, bound.expand_as(x).contiguous())
    if maximum is not None:
        bound = torch.as_tensor(maximum, device=x.device, dtype=x.dtype)
        x = torch.minimum(x, bound.expand_as(x).contiguous())
    return x


@contextmanager
def directml_t5_compat():
    """Patch only the worker's T5 namespace; never global Torch or disk files."""
    from transformers.models.t5 import modeling_t5

    original = modeling_t5.torch

    class TorchProxy:
        def __getattr__(self, name):
            return getattr(original, name)

        def clamp(self, x, min=None, max=None, *, out=None):
            if x.device.type != "privateuseone":
                return original.clamp(x, min=min, max=max, out=out)
            result = tensor_bound_clamp(x, min, max)
            if out is not None:
                out.copy_(result)
                return out
            return result

    modeling_t5.torch = TorchProxy()
    try:
        yield
    finally:
        modeling_t5.torch = original


def unfused_lstm_forward(self, x, hx=None):
    """Standard LSTM gates using real GPU kernels; inference only.

    DirectML 0.2.5 cannot execute the fused cell used by the codec's LSTM.
    Precompute input projections, then keep recurrent states on the GPU.
    """
    import torch
    import torch.nn.functional as functional

    if self.training or self.bidirectional or self.proj_size or x.ndim != 3:
        raise ValueError("Only evaluation of unidirectional, unprojected 3-D LSTM is supported")
    if not self.batch_first:
        x = x.transpose(0, 1)
    if hx is None:
        state_shape = (self.num_layers, x.shape[0], self.hidden_size)
        hx = (x.new_zeros(state_shape), x.new_zeros(state_shape))
    hidden, cells = [], []
    for layer in range(self.num_layers):
        h, c = hx[0][layer].contiguous(), hx[1][layer].contiguous()
        projected = functional.linear(
            x, getattr(self, f"weight_ih_l{layer}"), getattr(self, f"bias_ih_l{layer}", None)
        )
        frames = []
        for frame in projected.unbind(1):
            gates = frame.contiguous() + functional.linear(
                h, getattr(self, f"weight_hh_l{layer}"), getattr(self, f"bias_hh_l{layer}", None)
            )
            i, f, g, o = gates.chunk(4, dim=-1)
            c = f.sigmoid() * c + i.sigmoid() * g.tanh()
            h = o.sigmoid() * c.tanh()
            frames.append(h)
        x = torch.stack(frames, dim=1)
        hidden.append(h)
        cells.append(c)
    if not self.batch_first:
        x = x.transpose(0, 1)
    return x, (torch.stack(hidden), torch.stack(cells))


def configure_codec(model):
    import torch

    for layer in model.modules():
        if hasattr(layer, "weight_g") and hasattr(layer, "weight_v"):
            torch.nn.utils.remove_weight_norm(layer)
        if isinstance(layer, torch.nn.LSTM):
            layer.forward = types.MethodType(unfused_lstm_forward, layer)
        if isinstance(layer, torch.nn.ELU):
            layer.forward = types.MethodType(real_elu_forward, layer)
    configure_pointwise_convs(model)
    return model


def configure_pointwise_convs(model):
    """Avoid explicit F.pad(x, (0, 0)), which corrupts data on this DML runtime.

    Upstream causal/patcher convolution wrappers call pad even when it adds no
    samples. A unit kernel at stride 1 needs no such call. Learned weights and
    the convolution remain on the GPU; no watermark or model branch is removed.
    """
    import torch

    for layer in model.modules():
        if (
            isinstance(layer, torch.nn.Conv1d)
            and layer.kernel_size == (1,)
            and layer.stride == (1,)
            and layer.padding == (0,)
            and layer.padding_mode == "zeros"
        ):
            layer.forward = types.MethodType(pointwise_conv_forward, layer)
    return model


def pointwise_conv_forward(self, x):
    import torch.nn.functional as functional

    return functional.conv1d(
        x, self.weight, self.bias, self.stride, self.padding, self.dilation, self.groups
    )


def real_elu_forward(self, x):
    """ELU via supported real kernels rather than DirectML's CPU fallback."""
    import torch

    negative = self.alpha * (torch.minimum(x, torch.zeros_like(x)).exp() - 1)
    return torch.where(x > 0, x, negative)
