import asyncio
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT / "backend"))

from app.langgraph.docs_agent.agent import create_docs_agent  # noqa: E402


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def get_changed_files(base_ref: str) -> list[str]:
    merge_base = git("merge-base", base_ref, "HEAD")
    output = git("diff", "--name-only", f"{merge_base}...HEAD")
    return [line for line in output.splitlines() if line.strip()]


def get_diff_stat(base_ref: str) -> str:
    merge_base = git("merge-base", base_ref, "HEAD")
    return git("diff", "--stat", f"{merge_base}...HEAD")


def get_worktree_changes() -> list[str]:
    output = git("status", "--porcelain")
    changed: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        changed.append(path)
    return changed


def normalize_paths(paths: list[str]) -> set[str]:
    return {path.replace("\\", "/") for path in paths}


async def main() -> None:
    base_ref = "origin/main"
    if len(sys.argv) > 1:
        base_ref = sys.argv[1]

    changed_files = get_changed_files(base_ref)
    if not changed_files:
        print("No changed files detected. Nothing to document.")
        return

    baseline_changes = normalize_paths(get_worktree_changes())

    changed_file_lines = "\n".join(f"- {path}" for path in changed_files)
    diff_stat = get_diff_stat(base_ref)
    docs_files = sorted(
        str(path.relative_to(ROOT / "docs")).replace("\\", "/")
        for path in (ROOT / "docs").rglob("*.md")
    )
    docs_file_lines = "\n".join(f"- {path}" for path in docs_files)

    agent = create_docs_agent()
    result = await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Update the project documentation under /workspace/docs based on the current code changes.\n\n"
                        f"Base ref: {base_ref}\n\n"
                        "Changed files:\n"
                        f"{changed_file_lines}\n\n"
                        "Existing docs files under /docs/:\n"
                        f"{docs_file_lines}\n\n"
                        "Diff stat:\n"
                        f"{diff_stat}\n\n"
                        "Read the changed-file context, compare with the docs under /docs/, and update only the docs that are affected. "
                        "Edit only /docs/ files and do not create nested paths like /docs/docs/ or /workspace/docs/."
                    ),
                }
            ]
        },
        config={"configurable": {"thread_id": f"docs-agent-{uuid4()}"}},
    )

    print("Docs agent run completed.")
    messages = result.get("messages", [])
    if messages:
        last = messages[-1]
        content = getattr(last, "content", "")
        print(content if isinstance(content, str) else str(content))

    changed_paths = normalize_paths(get_worktree_changes())
    new_changes = sorted(changed_paths - baseline_changes)
    non_docs_changes = [path for path in new_changes if not path.startswith("docs/")]
    if non_docs_changes:
        raise RuntimeError(
            "Docs agent modified files outside docs/: "
            + ", ".join(sorted(non_docs_changes))
        )


if __name__ == "__main__":
    asyncio.run(main())
