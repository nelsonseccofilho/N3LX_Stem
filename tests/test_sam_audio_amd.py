"""Numerical checks for the local DirectML rotary adaptation, without weights."""

from types import SimpleNamespace

import pytest
import torch

from scripts.sam_audio_amd_compat import configure_codec, real_rotary_forward, tensor_bound_clamp


@pytest.mark.parametrize("bhle", [False, True])
@pytest.mark.parametrize("dtype", [torch.float32, torch.float16])
@pytest.mark.parametrize("batch,length,heads,dim", [(1, 1, 1, 8), (2, 17, 4, 16)])
def test_real_rotary_matches_upstream_math(bhle, dtype, batch, length, heads, dim):
    torch.manual_seed(42)
    angles = torch.randn(length + 3, dim // 2)
    cos, sin = angles.cos(), angles.sin()
    freqs = torch.stack((cos, -sin, sin, cos), dim=-1).view(1, length + 3, 1, dim // 2, 2, 2)
    freqs = freqs.to(dtype)
    x = torch.randn(batch, length, heads, dim).to(dtype)
    expected = (
        (x.reshape(batch, length, heads, dim // 2, 1, 2) * freqs[:, :length]).sum(5).flatten(3)
    )
    if bhle:
        x, expected = x.transpose(1, 2), expected.transpose(1, 2)
    result = real_rotary_forward(SimpleNamespace(freqs_cis=freqs), x, bhle=bhle)
    assert result.device == x.device
    assert result.dtype == x.dtype
    torch.testing.assert_close(
        result,
        expected,
        atol=0.004 if dtype == torch.float16 else 1e-6,
        rtol=0.004 if dtype == torch.float16 else 1e-6,
    )


@pytest.mark.parametrize("layers", [1, 2])
@pytest.mark.parametrize("batch_first", [False, True])
@pytest.mark.parametrize("bias", [False, True])
@pytest.mark.parametrize("initial", [False, True])
def test_unfused_lstm_preserves_weights_states_and_results(layers, batch_first, bias, initial):
    torch.manual_seed(42)
    model = torch.nn.LSTM(3, 4, num_layers=layers, batch_first=batch_first, bias=bias).eval()
    original_weights = {k: v.clone() for k, v in model.state_dict().items()}
    x = torch.randn((2, 5, 3) if batch_first else (5, 2, 3))
    hx = (torch.randn(layers, 2, 4), torch.randn(layers, 2, 4)) if initial else None
    with torch.no_grad():
        expected, expected_states = model(x, hx)
        configure_codec(model)
        actual, actual_states = model(x, hx)
    torch.testing.assert_close(actual, expected)
    for got, wanted in zip(actual_states, expected_states, strict=True):
        torch.testing.assert_close(got, wanted)
    for name, value in model.state_dict().items():
        assert torch.equal(value, original_weights[name])


@pytest.mark.parametrize("dtype", [torch.float32, torch.float16])
def test_t5_scalar_clamp_preserves_inf_nan_and_limits(dtype):
    x = torch.tensor([-float("inf"), -10, -1, 0, 1, 10, float("inf"), float("nan")], dtype=dtype)
    bound = torch.tensor(3.0, dtype=torch.float32)
    torch.testing.assert_close(
        tensor_bound_clamp(x, -bound, bound), torch.clamp(x, min=-bound, max=bound), equal_nan=True
    )


def test_codec_materializes_weight_norm_without_changing_output():
    torch.manual_seed(42)
    model = torch.nn.Sequential(torch.nn.utils.weight_norm(torch.nn.Conv1d(2, 4, 3))).eval()
    x = torch.randn(1, 2, 16)
    with torch.no_grad():
        expected = model(x)
        configure_codec(model)
        actual = model(x)
    torch.testing.assert_close(actual, expected)
    assert not hasattr(model[0], "weight_g")


@pytest.mark.parametrize("alpha", [0.5, 1.0, 2.0])
def test_real_elu_preserves_output(alpha):
    x = torch.linspace(-15, 15, 100)
    layer = torch.nn.ELU(alpha).eval()
    expected = layer(x)
    configure_codec(layer)
    torch.testing.assert_close(layer(x), expected)


@pytest.mark.parametrize("bias", [False, True])
@pytest.mark.parametrize("groups", [1, 2])
@pytest.mark.parametrize("length", [17, 24960])
def test_pointwise_convolution_avoids_noop_pad_without_changing_audio(bias, groups, length):
    class CausalPointwise(torch.nn.Conv1d):
        def forward(self, x):
            return super().forward(torch.nn.functional.pad(x, (0, 0)))

    torch.manual_seed(42)
    layer = CausalPointwise(4, 8, 1, groups=groups, bias=bias).eval()
    # An offset view also verifies preservation of input samples and channel layout.
    x = torch.randn(2, 4, length + 3)[..., 3:]
    original = x.clone()
    with torch.no_grad():
        reference = layer(x)
        configure_codec(layer)
        result = layer(x)
    torch.testing.assert_close(result, reference)
    assert torch.equal(x, original)
