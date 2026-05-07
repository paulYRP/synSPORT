"""
Initialize TabSyn source package defaults.

Description:
    This module is part of the TabSyn integration used by the synSPORT
    pipeline for tabular synthetic-data generation.

Input:
    Module-specific function arguments, command-line arguments, or dataset files.

Output:
    Transformed datasets, trained models, generated samples, metrics, or helper values.
"""

import torch
from icecream import install

torch.set_num_threads(1)
install()

from . import env  # noqa
from .data import *  # noqa
from .deep import *  # noqa
from .env import *  # noqa
from .metrics import *  # noqa
from .util import *  # noqa
