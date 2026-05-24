import pytest
from app.schema.enums import AttemptCorrectness
from app.validators import deepagent_validator
from app.validators.deepagent_validator import validate_code_submission
from app.validators.schemas import CodeValidationRequest, CodeValidationResult


class FakeStructuredAgent:
    async def ainvoke(self, _payload):
        return {
            "structured_response": CodeValidationResult(
                correctness=AttemptCorrectness.CORRECT,
                has_serious_blocker=False,
                validation_strategy="reasoned_from_external_execution",
                feedback_summary="The submitted code matches the requested behavior.",
                confidence_score=0.86,
            )
        }


@pytest.mark.asyncio
async def test_validate_code_submission_prefers_structured_response(monkeypatch):
    monkeypatch.setattr(
        "app.validators.deepagent_validator.create_code_validator_agent",
        lambda **_kwargs: FakeStructuredAgent(),
    )

    result = await validate_code_submission(
        CodeValidationRequest(
            user_id="user-1",
            skillpath_id="sp-1",
            content_id="cp-1",
            language="python",
            coding_problem_prompt="Return the sum of two numbers.",
            submitted_code="def add(a, b): return a + b",
        ),
        backend=object(),
    )

    assert result.correctness == AttemptCorrectness.CORRECT
    assert result.validation_strategy == "reasoned_from_external_execution"


def test_create_code_validator_agent_uses_structured_response_format(monkeypatch):
    captured_kwargs = {}

    def fake_create_deep_agent(**kwargs):
        captured_kwargs.update(kwargs)
        return object()

    monkeypatch.setattr(
        deepagent_validator, "create_deep_agent", fake_create_deep_agent
    )

    agent = deepagent_validator.create_code_validator_agent(backend=object())

    assert agent is not None
    assert captured_kwargs["response_format"] is CodeValidationResult


def test_validation_prompt_includes_external_execution_evidence():
    prompt = deepagent_validator._build_validation_prompt(
        CodeValidationRequest(
            user_id="user-1",
            skillpath_id="sp-1",
            content_id="cp-1",
            language="python",
            coding_problem_prompt="Print x.",
            submitted_code="print(x)",
            runtime_error="NameError: name 'x' is not defined",
            stdout="",
            stderr="Traceback...",
        )
    )

    assert "NameError: name 'x' is not defined" in prompt
    assert "external compile/runtime/test evidence" in prompt
