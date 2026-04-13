import os

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
DOCS_ROOT = os.path.join(REPO_ROOT, "docs")
SKILLS_DIR = os.path.join(os.path.dirname(__file__), "skills")
DOCS_AGENT_MODEL = os.getenv("DOCS_AGENT_MODEL", "google_genai:gemini-3-flash-preview")

_SYSTEM_PROMPT = """You are a docs maintenance agent.

Your job is to update project documentation based on code changes.
Use the code-change context provided in the user request, inspect the existing docs under /docs/, and update only the docs that are actually affected.
Keep documentation concise, accurate, and consistent with the current codebase.
Do not invent features or workflows that are not present in the code.
The workspace is repo-root shaped.
Documentation files live under /docs/.
Skills live under /skills/.
Edit only files under /docs/.
Do not create nested paths like /docs/docs/ or /workspace/docs/.
"""


def create_docs_agent():
    """Create a deep agent that can update repository docs."""
    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/docs/": FilesystemBackend(root_dir=DOCS_ROOT, virtual_mode=True),
            "/skills/": FilesystemBackend(root_dir=SKILLS_DIR, virtual_mode=True),
        },
    )

    return create_deep_agent(
        model=DOCS_AGENT_MODEL,
        system_prompt=_SYSTEM_PROMPT,
        backend=backend,
        skills=["/skills/"],
    )
