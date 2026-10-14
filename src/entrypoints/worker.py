"""Workflow worker entrypoint: register the GitHub push workflow and start."""

import asyncio
import sys
from pathlib import Path

# Make the project root importable regardless of the working directory.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mistralai.workflows import run_worker
from src.workflows.github_push import GithubPushWorkflow


async def main() -> None:
    await run_worker([GithubPushWorkflow])


if __name__ == "__main__":
    asyncio.run(main())
