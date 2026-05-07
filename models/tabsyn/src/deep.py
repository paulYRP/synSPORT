"""
Provide neural-network training helpers used by TabSyn components.

Description:
    This module is part of the TabSyn integration used by the synSPORT
    pipeline for tabular synthetic-data generation.

Input:
    Module-specific function arguments, command-line arguments, or dataset files.

Output:
    Transformed datasets, trained models, generated samples, metrics, or helper values.
"""

import statistics
from dataclasses import dataclass
from typing import Any, Callable, Literal, cast

# import rtdl
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import zero
from torch import Tensor

from .util import TaskType


def cos_sin(x: Tensor) -> Tensor:
    """
    Description:
        Compute cosine-sine features for `cos_sin`.

    Input:
        x: Tensor.

    Output:
        Tensor.
    """
    return torch.cat([torch.cos(x), torch.sin(x)], -1)


@dataclass
class PeriodicOptions:
    n: int  # the output size is 2 * n
    sigma: float
    trainable: bool
    initialization: Literal['log-linear', 'normal']


class Periodic(nn.Module):
    def __init__(self, n_features: int, options: PeriodicOptions) -> None:
        """
        Description:
            Initialize `Periodic` with the parameters required by later methods.

        Input:
            n_features: int; options: PeriodicOptions.

        Output:
            None; the function performs file, state, logging, model-training, or tensor side effects.
        """
        super().__init__()
        if options.initialization == 'log-linear':
            coefficients = options.sigma ** (torch.arange(options.n) / options.n)
            coefficients = coefficients[None].repeat(n_features, 1)
        else:
            assert options.initialization == 'normal'
            coefficients = torch.normal(0.0, options.sigma, (n_features, options.n))
        if options.trainable:
            self.coefficients = nn.Parameter(coefficients)  # type: ignore[code]
        else:
            self.register_buffer('coefficients', coefficients)

    def forward(self, x: Tensor) -> Tensor:
        """
        Description:
            Run the forward pass for `Periodic`.

        Input:
            x: Tensor.

        Output:
            Tensor.
        """
        assert x.ndim == 2
        return cos_sin(2 * torch.pi * self.coefficients[None] * x[..., None])


def get_n_parameters(m: nn.Module):
    """
    Description:
        Return values for `get_n_parameters`.

    Input:
        m: nn.Module.

    Output:
        Computed value returned by the function.
    """
    return sum(x.numel() for x in m.parameters() if x.requires_grad)


def get_loss_fn(task_type: TaskType) -> Callable[..., Tensor]:
    """
    Description:
        Return values for `get_loss_fn`.

    Input:
        task_type: TaskType.

    Output:
        Callable[..., Tensor].
    """
    return (
        F.binary_cross_entropy_with_logits
        if task_type == TaskType.BINCLASS
        else F.cross_entropy
        if task_type == TaskType.MULTICLASS
        else F.mse_loss
    )


def default_zero_weight_decay_condition(module_name, module, parameter_name, parameter):
    """
    Description:
        Return default settings for `default_zero_weight_decay_condition`.

    Input:
        module_name; module; parameter_name; parameter.

    Output:
        Computed value returned by the function.
    """
    del module_name, parameter
    return parameter_name.endswith('bias') or isinstance(
        module,
        (
            nn.BatchNorm1d,
            nn.LayerNorm,
            nn.InstanceNorm1d,
            rtdl.CLSToken,
            rtdl.NumericalFeatureTokenizer,
            rtdl.CategoricalFeatureTokenizer,
            Periodic,
        ),
    )


def split_parameters_by_weight_decay(
    model: nn.Module, zero_weight_decay_condition=default_zero_weight_decay_condition
) -> list[dict[str, Any]]:
    """
    Description:
        Split data for `split_parameters_by_weight_decay`.

    Input:
        model: nn.Module; zero_weight_decay_condition.

    Output:
        list[dict[str, Any]].
    """
    parameters_info = {}
    for module_name, module in model.named_modules():
        for parameter_name, parameter in module.named_parameters():
            full_parameter_name = (
                f'{module_name}.{parameter_name}' if module_name else parameter_name
            )
            parameters_info.setdefault(full_parameter_name, ([], parameter))[0].append(
                zero_weight_decay_condition(
                    module_name, module, parameter_name, parameter
                )
            )
    params_with_wd = {'params': []}
    params_without_wd = {'params': [], 'weight_decay': 0.0}
    for full_parameter_name, (results, parameter) in parameters_info.items():
        (params_without_wd if any(results) else params_with_wd)['params'].append(
            parameter
        )
    return [params_with_wd, params_without_wd]


def make_optimizer(
    config: dict[str, Any],
    parameter_groups,
) -> optim.Optimizer:
    """
    Description:
        Create objects for `make_optimizer`.

    Input:
        config: dict[str, Any]; parameter_groups.

    Output:
        optim.Optimizer.
    """
    if config['optimizer'] == 'FT-Transformer-default':
        return optim.AdamW(parameter_groups, lr=1e-4, weight_decay=1e-5)
    return getattr(optim, config['optimizer'])(
        parameter_groups,
        **{x: config[x] for x in ['lr', 'weight_decay', 'momentum'] if x in config},
    )


def get_lr(optimizer: optim.Optimizer) -> float:
    """
    Description:
        Return values for `get_lr`.

    Input:
        optimizer: optim.Optimizer.

    Output:
        float.
    """
    return next(iter(optimizer.param_groups))['lr']


def is_oom_exception(err: RuntimeError) -> bool:
    """
    Description:
        Check whether data satisfies `is_oom_exception`.

    Input:
        err: RuntimeError.

    Output:
        bool.
    """
    return any(
        x in str(err)
        for x in [
            'CUDA out of memory',
            'CUBLAS_STATUS_ALLOC_FAILED',
            'CUDA error: out of memory',
        ]
    )


def train_with_auto_virtual_batch(
    optimizer,
    loss_fn,
    step,
    batch,
    chunk_size: int,
) -> tuple[Tensor, int]:
    """
    Description:
        Train data for `train_with_auto_virtual_batch`.

    Input:
        optimizer; loss_fn; step; batch; chunk_size: int.

    Output:
        tuple[Tensor, int].
    """
    batch_size = len(batch)
    random_state = zero.random.get_state()
    loss = None
    while chunk_size != 0:
        try:
            zero.random.set_state(random_state)
            optimizer.zero_grad()
            if batch_size <= chunk_size:
                loss = loss_fn(*step(batch))
                loss.backward()
            else:
                loss = None
                for chunk in zero.iter_batches(batch, chunk_size):
                    chunk_loss = loss_fn(*step(chunk))
                    chunk_loss = chunk_loss * (len(chunk) / batch_size)
                    chunk_loss.backward()
                    if loss is None:
                        loss = chunk_loss.detach()
                    else:
                        loss += chunk_loss.detach()
        except RuntimeError as err:
            if not is_oom_exception(err):
                raise
            chunk_size //= 2
        else:
            break
    if not chunk_size:
        raise RuntimeError('Not enough memory even for batch_size=1')
    optimizer.step()
    return cast(Tensor, loss), chunk_size


def process_epoch_losses(losses: list[Tensor]) -> tuple[list[float], float]:
    """
    Description:
        Process data for `process_epoch_losses`.

    Input:
        losses: list[Tensor].

    Output:
        tuple[list[float], float].
    """
    losses_ = torch.stack(losses).tolist()
    return losses_, statistics.mean(losses_)
