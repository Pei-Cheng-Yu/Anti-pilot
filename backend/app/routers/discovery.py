import uuid

from app.db.session import get_session
from app.langgraph.discovery_agent.schemas import DiscoveryResponse, ResumeRequest
from app.services.discovery import (
    get_discovery_conversation_context,
    get_discovery_conversation_user_id,
    save_discovery_conversation,
)
from app.services.discovery_agent_server import (
    DiscoveryAgentRequestError,
    DiscoveryAgentUnavailableError,
    DiscoveryResumeError,
    resume_discovery_with_agent_server,
    send_discovery_message_to_agent_server,
)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/discovery", tags=["discovery"])


class CreateDiscoveryConversationRequest(BaseModel):
    user_id: str
    goal_id: str | None = None


class CreateDiscoveryConversationResponse(BaseModel):
    conversation_id: str


class DiscoveryMessageRequest(BaseModel):
    message: str


async def _conversation_user_or_404(conversation_id: str) -> str:
    async with get_session() as session:
        try:
            return await get_discovery_conversation_user_id(conversation_id, session)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e


async def _conversation_context_or_404(conversation_id: str) -> tuple[str, str | None]:
    async with get_session() as session:
        try:
            return await get_discovery_conversation_context(conversation_id, session)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/conversations", response_model=CreateDiscoveryConversationResponse)
async def create_discovery_conversation(request: CreateDiscoveryConversationRequest):
    conversation_id = str(uuid.uuid4())
    async with get_session() as session:
        await save_discovery_conversation(
            request.user_id,
            conversation_id,
            session,
            goal_id=request.goal_id,
        )
    return CreateDiscoveryConversationResponse(conversation_id=conversation_id)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=DiscoveryResponse,
)
async def send_discovery_message(
    conversation_id: str, request: DiscoveryMessageRequest
):
    user_id, goal_id = await _conversation_context_or_404(conversation_id)
    try:
        return await send_discovery_message_to_agent_server(
            conversation_id=conversation_id,
            user_id=user_id,
            goal_id=goal_id,
            message=request.message,
        )
    except DiscoveryAgentRequestError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except DiscoveryAgentUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.post(
    "/conversations/{conversation_id}/resume",
    response_model=DiscoveryResponse,
)
async def resume_discovery_conversation(conversation_id: str, request: ResumeRequest):
    user_id, goal_id = await _conversation_context_or_404(conversation_id)
    try:
        return await resume_discovery_with_agent_server(
            conversation_id=conversation_id,
            user_id=user_id,
            goal_id=goal_id,
            selection=request.selection,
        )
    except DiscoveryResumeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except DiscoveryAgentRequestError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except DiscoveryAgentUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
