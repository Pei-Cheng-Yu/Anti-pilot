import json
from typing import Literal, NotRequired, TypedDict

from pydantic import BaseModel, Field, ValidationError, field_validator


class UIHints(BaseModel):
    type: Literal["single_choice", "multi_choice", "text_input", "confirm"]
    options: list[str] = Field(default_factory=list)

    @field_validator("options")
    @classmethod
    def require_options_for_choice_types(cls, options: list[str], info) -> list[str]:
        hint_type = info.data.get("type")
        if hint_type in {"single_choice", "multi_choice"} and not options:
            raise ValueError("choice ui_hints require non-empty options")
        return options


class DiscoveryResponse(BaseModel):
    message: str
    ui_hints: UIHints | None = None
    session_complete: bool = False
    roadmap_job_id: str | None = None
    roadmap_status: str | None = None


class DiscoveryContext(TypedDict):
    user_id: str
    conversation_id: NotRequired[str]
    goal_id: NotRequired[str]


class ResumeRequest(BaseModel):
    selection: str


def parse_discovery_response(raw: DiscoveryResponse | dict | str) -> DiscoveryResponse:
    """Parse a model result into DiscoveryResponse, falling back to raw text."""
    if isinstance(raw, DiscoveryResponse):
        return raw

    if isinstance(raw, dict):
        try:
            return DiscoveryResponse.model_validate(raw)
        except ValidationError:
            return DiscoveryResponse(message=str(raw))

    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return DiscoveryResponse(message=str(raw))

    try:
        return DiscoveryResponse.model_validate(parsed)
    except ValidationError:
        return DiscoveryResponse(message=str(raw))
