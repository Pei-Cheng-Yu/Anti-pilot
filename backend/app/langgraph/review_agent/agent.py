import os

from deepagents import create_deep_agent
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "skills")
REVIEW_AGENT_MODEL = os.getenv("REVIEW_AGENT_MODEL") or "gemini-3-flash-preview"

_SYSTEM_PROMPT = """You are a code review agent.

Review the provided code-change context and produce a concise, helpful review.
Focus on:
- what changed
- likely risks or regressions
- missing tests
- practical suggestions

This review is advisory and non-blocking.
Be concise and specific. Do not invent files or behavior that are not present in the provided diff context.
"""


def create_review_agent():
    """Create the non-blocking review agent."""
    model = ChatGoogleGenerativeAI(model=REVIEW_AGENT_MODEL)
    return create_deep_agent(
        model=model,
        system_prompt=_SYSTEM_PROMPT,
        skills=[SKILLS_DIR],
    )
