"""Workflow worker entrypoint."""

import asyncio


async def main() -> None:
    # Support both SDK layouts (newer namespace package and legacy top-level).
    try:
        from mistralai.workflows import run_worker
        from mistralai.workflows.discovery import discover_workflows
    except ImportError:
        import mistralai_workflows
        from mistralai_workflows import run_worker
        from mistralai_workflows.discovery import discover_workflows

    discovered = discover_workflows()
    await run_worker(discovered)


if __name__ == "__main__":
    asyncio.run(main())
