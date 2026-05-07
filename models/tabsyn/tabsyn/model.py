"""
Define TabSyn diffusion model, denoising network, embeddings, and activations.

Description:
    This module is part of the TabSyn integration used by the synSPORT
    pipeline for tabular synthetic-data generation.

Input:
    Module-specific function arguments, command-line arguments, or dataset files.

Output:
    Transformed datasets, trained models, generated samples, metrics, or helper values.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union, cast

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim
from torch import Tensor
from tabsyn.diffusion_utils import EDMLoss

ModuleType = Union[str, Callable[..., nn.Module]]

class SiLU(nn.Module):
    def forward(self, x):
        """
        Description:
            Run the forward pass for `SiLU`.

        Input:
            x.

        Output:
            Computed value returned by the function.
        """
        return x * torch.sigmoid(x)

class PositionalEmbedding(torch.nn.Module):
    def __init__(self, num_channels, max_positions=10000, endpoint=False):
        """
        Description:
            Initialize `PositionalEmbedding` with the parameters required by later methods.

        Input:
            num_channels; max_positions; endpoint.

        Output:
            None; the function performs file, state, logging, model-training, or tensor side effects.
        """
        super().__init__()
        self.num_channels = num_channels
        self.max_positions = max_positions
        self.endpoint = endpoint

    def forward(self, x):
        """
        Description:
            Run the forward pass for `PositionalEmbedding`.

        Input:
            x.

        Output:
            Computed value returned by the function.
        """
        freqs = torch.arange(start=0, end=self.num_channels//2, dtype=torch.float32, device=x.device)
        freqs = freqs / (self.num_channels // 2 - (1 if self.endpoint else 0))
        freqs = (1 / self.max_positions) ** freqs
        x = x.ger(freqs.to(x.dtype))
        x = torch.cat([x.cos(), x.sin()], dim=1)
        return x

def reglu(x: Tensor) -> Tensor:
    """
    Description:
        Apply ReGLU activation for `reglu`.

    Input:
        x: Tensor.

    Output:
        Tensor.

    Notes:
        The ReGLU activation function.
    """
    assert x.shape[-1] % 2 == 0
    a, b = x.chunk(2, dim=-1)
    return a * F.relu(b)


def geglu(x: Tensor) -> Tensor:
    """
    Description:
        Run processing for `geglu`.

    Input:
        x: Tensor.

    Output:
        Tensor.

    Notes:
        The GEGLU activation function.
    """
    assert x.shape[-1] % 2 == 0
    a, b = x.chunk(2, dim=-1)
    return a * F.gelu(b)

class ReGLU(nn.Module):
    """The ReGLU activation function.

    Examples:
        .. testcode::

            module = ReGLU()
            x = torch.randn(3, 4)
            assert module(x).shape == (3, 2)

    """

    def forward(self, x: Tensor) -> Tensor:
        """
        Description:
            Run the forward pass for `ReGLU`.

        Input:
            x: Tensor.

        Output:
            Tensor.
        """
        return reglu(x)


class GEGLU(nn.Module):
    """The GEGLU activation function.

    Examples:
        .. testcode::

            module = GEGLU()
            x = torch.randn(3, 4)
            assert module(x).shape == (3, 2)

    """

    def forward(self, x: Tensor) -> Tensor:
        """
        Description:
            Run the forward pass for `GEGLU`.

        Input:
            x: Tensor.

        Output:
            Tensor.
        """
        return geglu(x)


class FourierEmbedding(torch.nn.Module):
    def __init__(self, num_channels, scale=16):
        """
        Description:
            Initialize `FourierEmbedding` with the parameters required by later methods.

        Input:
            num_channels; scale.

        Output:
            None; the function performs file, state, logging, model-training, or tensor side effects.
        """
        super().__init__()
        self.register_buffer('freqs', torch.randn(num_channels // 2) * scale)

    def forward(self, x):
        """
        Description:
            Run the forward pass for `FourierEmbedding`.

        Input:
            x.

        Output:
            Computed value returned by the function.
        """
        x = x.ger((2 * np.pi * self.freqs).to(x.dtype))
        x = torch.cat([x.cos(), x.sin()], dim=1)
        return x

class MLPDiffusion(nn.Module):
    def __init__(self, d_in, dim_t = 512):
        """
        Description:
            Initialize `MLPDiffusion` with the parameters required by later methods.

        Input:
            d_in; dim_t.

        Output:
            None; the function performs file, state, logging, model-training, or tensor side effects.
        """
        super().__init__()
        self.dim_t = dim_t

        self.proj = nn.Linear(d_in, dim_t)

        self.mlp = nn.Sequential(
            nn.Linear(dim_t, dim_t * 2),
            nn.SiLU(),
            nn.Linear(dim_t * 2, dim_t * 2),
            nn.SiLU(),
            nn.Linear(dim_t * 2, dim_t),
            nn.SiLU(),
            nn.Linear(dim_t, d_in),
        )

        self.map_noise = PositionalEmbedding(num_channels=dim_t)
        self.time_embed = nn.Sequential(
            nn.Linear(dim_t, dim_t),
            nn.SiLU(),
            nn.Linear(dim_t, dim_t)
        )
    
    def forward(self, x, noise_labels, class_labels=None):
        """
        Description:
            Run the forward pass for `MLPDiffusion`.

        Input:
            x; noise_labels; class_labels.

        Output:
            Computed value returned by the function.
        """
        emb = self.map_noise(noise_labels)
        emb = emb.reshape(emb.shape[0], 2, -1).flip(1).reshape(*emb.shape) # swap sin/cos
        emb = self.time_embed(emb)
    
        x = self.proj(x) + emb
        return self.mlp(x)


class Precond(nn.Module):
    def __init__(self,
        denoise_fn,
        hid_dim,
        sigma_min = 0,                # Minimum supported noise level.
        sigma_max = float('inf'),     # Maximum supported noise level.
        sigma_data = 0.5,              # Expected standard deviation of the training data.
    ):
        """
        Description:
            Initialize `Precond` with the parameters required by later methods.

        Input:
            denoise_fn; hid_dim; sigma_min; sigma_max; sigma_data.

        Output:
            None; the function performs file, state, logging, model-training, or tensor side effects.
        """
        super().__init__()

        self.hid_dim = hid_dim
        self.sigma_min = sigma_min
        self.sigma_max = sigma_max
        self.sigma_data = sigma_data
        ###########
        self.denoise_fn_F = denoise_fn

    def forward(self, x, sigma):

        """
        Description:
            Run the forward pass for `Precond`.

        Input:
            x; sigma.

        Output:
            Computed value returned by the function.
        """
        x = x.to(torch.float32)

        sigma = sigma.to(torch.float32).reshape(-1, 1)
        dtype = torch.float32

        c_skip = self.sigma_data ** 2 / (sigma ** 2 + self.sigma_data ** 2)
        c_out = sigma * self.sigma_data / (sigma ** 2 + self.sigma_data ** 2).sqrt()
        c_in = 1 / (self.sigma_data ** 2 + sigma ** 2).sqrt()
        c_noise = sigma.log() / 4

        x_in = c_in * x
        F_x = self.denoise_fn_F((x_in).to(dtype), c_noise.flatten())

        assert F_x.dtype == dtype
        D_x = c_skip * x + c_out * F_x.to(torch.float32)
        return D_x

    def round_sigma(self, sigma):
        """
        Description:
            Round values for `round_sigma`.

        Input:
            sigma.

        Output:
            Computed value returned by the function.
        """
        return torch.as_tensor(sigma)
    

class Model(nn.Module):
    def __init__(self, denoise_fn, hid_dim, P_mean=-1.2, P_std=1.2, sigma_data=0.5, gamma=5, opts=None, pfgmpp = False):
        """
        Description:
            Initialize `Model` with the parameters required by later methods.

        Input:
            denoise_fn; hid_dim; P_mean; P_std; sigma_data; gamma; opts; pfgmpp.

        Output:
            None; the function performs file, state, logging, model-training, or tensor side effects.
        """
        super().__init__()

        self.denoise_fn_D = Precond(denoise_fn, hid_dim)
        self.loss_fn = EDMLoss(P_mean, P_std, sigma_data, hid_dim=hid_dim, gamma=5, opts=None)

    def forward(self, x):

        """
        Description:
            Run the forward pass for `Model`.

        Input:
            x.

        Output:
            Computed value returned by the function.
        """
        loss = self.loss_fn(self.denoise_fn_D, x)
        return loss.mean(-1).mean()
