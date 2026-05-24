from app.db.session import get_session
from app.schema.entities import (
    CodeCorrectionRequest,
    CodeCorrectionResult,
    CodeSubmissionResult,
)
from app.services import code_correction as service
from app.validators.schemas import CodeValidationRequest
from fastmcp import FastMCP

code_correction_mcp = FastMCP("code_correction")


@code_correction_mcp.tool()
async def process_code_correction(
    request: CodeCorrectionRequest,
) -> CodeCorrectionResult:
    """
    Assemble learner memory for a coding submission, normalize evaluator signals,
    and persist the attempt plus any consolidated memory updates.

    This is the first correction-pipeline entrypoint. A sandbox or external code
    evaluator can provide compile errors, runtime errors, and test results before
    calling this tool.
    """
    async with get_session() as session:
        return await service.process_code_correction(request, session)


@code_correction_mcp.tool()
async def submit_code_attempt(
    request: CodeValidationRequest,
) -> CodeSubmissionResult:
    """
    Validate a learner-submitted coding attempt, then persist the correction
    evidence and consolidate learner memory in one product-level call.
    """
    async with get_session() as session:
        return await service.submit_code_attempt(request, session)
