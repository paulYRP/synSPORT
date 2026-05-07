"""
Dispatch TabSyn training or sampling commands based on command-line arguments.

Description:
    This module is part of the TabSyn integration used by the synSPORT
    pipeline for tabular synthetic-data generation.

Input:
    Module-specific function arguments, command-line arguments, or dataset files.

Output:
    Transformed datasets, trained models, generated samples, metrics, or helper values.
"""

import torch
from utils import execute_function, get_args

if __name__ == '__main__':
    args = get_args()
    if args.gpu != -1 and torch.cuda.is_available():
        args.device = f'cuda:{args.gpu}'
    else:
        args.device = 'cpu'

    if not args.save_path:
        args.save_path = f'synthetic/{args.dataname}/{args.method}.csv'
    main_fn = execute_function(args.method, args.mode)

    main_fn(args)
