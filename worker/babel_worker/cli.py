from __future__ import annotations

import argparse
import sys
from pathlib import Path

from babel_worker import __version__
from babel_worker.config import Config
from babel_worker.loop import run


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="babel-worker",
        description="Pull-worker for babel. Claims jobs from the backend "
        "and runs them locally against llama-server.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to a config.env file. "
        "Default: ~/.config/babel-worker/config.env, then ./babel-worker.env",
    )
    parser.add_argument(
        "--version", action="version", version=f"babel-worker {__version__}"
    )

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    cfg = Config.from_env(args.config)
    run(cfg)
