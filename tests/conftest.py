"""Shared test setup.

Rich wraps output to the terminal width, and under pytest that width depends on
the environment — which made an assertion pass locally and fail in CI purely
because the tmp_path was a different length. Pin it.
"""

import os

os.environ["COLUMNS"] = "200"

from vaultwright.cli import console  # noqa: E402  (must follow the env var)

console.width = 200
