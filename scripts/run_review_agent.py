import asyncio
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT / "backend"))

from app.langgraph.review_agent.agent import create_review_agent  # noqa: E402

OUTPUT_PATH = ROOT / "review-agent-summary.md"


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


def get_diff_patch(base_ref: str) -> str:
    merge_base = git("merge-base", base_ref, "HEAD")
    return git("diff", "--unified=3", f"{merge_base}...HEAD")


def extract_last_text(result: dict) -> str:
    messages = result.get("messages", [])
    for message in reversed(messages):
        content = getattr(message, "content", "")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "").strip()
                    if text:
                        parts.append(text)
            if parts:
                return "\n".join(parts)
    return "No review output generated."


async def main() -> None:
    base_ref = "origin/main"
    if len(sys.argv) > 1:
        base_ref = sys.argv[1]

    changed_files = get_changed_files(base_ref)
    if not changed_files:
        summary = "# Review Agent\n\nNo changed files detected."
        OUTPUT_PATH.write_text(summary, encoding="utf-8")
        print(summary)
        return

    changed_file_lines = "\n".join(f"- {path}" for path in changed_files)
    diff_stat = get_diff_stat(base_ref)
    diff_patch = get_diff_patch(base_ref)

    if len(diff_patch) > 50000:
        diff_patch = diff_patch[:50000] + "\n\n[diff truncated]"

    agent = create_review_agent()
    result = await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Review the following code changes and provide a concise, non-blocking review.\n\n"
                        f"Base ref: {base_ref}\n\n"
                        "Changed files:\n"
                        f"{changed_file_lines}\n\n"
                        "Diff stat:\n"
                        f"{diff_stat}\n\n"
                        "Unified diff:\n"
                        f"{diff_patch}"
                    ),
                }
            ]
        },
        config={"configurable": {"thread_id": f"review-agent-{uuid4()}"}},
    )

    review_text = extract_last_text(result)
    OUTPUT_PATH.write_text(review_text, encoding="utf-8")
    print(review_text)


if __name__ == "__main__":
    asyncio.run(main())
