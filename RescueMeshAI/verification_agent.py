
import os
import json
import re
import logging
from openai import OpenAI

MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"

SYSTEM_PROMPT = """
You are the RescueMesh AI Verification Agent.

Compare emergency reports and return exactly one valid JSON object.

Use this schema:
{
  "verified_facts": [],
  "conflicting_information": [],
  "unknown_information": [],
  "confidence_score": 0,
  "human_verification_required": true
}

Rules:
1. Identify facts supported by multiple reports.
2. Identify contradictions between reports.
3. List important information that is missing.
4. Repeated reports are corroboration, not independent proof.
5. Never invent facts or claim something is confirmed without evidence.
6. confidence_score must be an integer from 0 to 100.
7. human_verification_required must always be true.
8. Keep each list concise.
9. Return JSON only, without Markdown or explanations.
"""


def _extract_json(raw: str) -> dict:
    """Parse a JSON object from the model response."""
    if not raw or not raw.strip():
        raise RuntimeError("The verification model returned empty output.")

    # Remove Markdown code fences if the model adds them.
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    # First, try parsing the entire response.
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Otherwise, try extracting the first JSON object.
    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start != -1 and end > start:
        try:
            result = json.loads(cleaned[start:end + 1])
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"The verification model returned invalid JSON: {exc}"
            ) from exc

    raise RuntimeError(
        f"The verification model did not return a valid JSON object. "
        f"Response preview: {cleaned[:300]}"
    )


def verify_reports(reports: list[str]) -> dict:
    """
    Compare two or more emergency reports.

    Returns:
        A structured dictionary containing corroborated facts,
        conflicting information, unknown information, and confidence.
    """

    if not isinstance(reports, list):
        raise ValueError("reports must be a list of strings.")

    cleaned_reports = [
        report.strip()
        for report in reports
        if isinstance(report, str) and report.strip()
    ]

    if len(cleaned_reports) < 2:
        return {
            "verified_facts": [],
            "conflicting_information": [],
            "unknown_information": [
                "At least two non-empty reports are required for comparison."
            ],
            "confidence_score": 0,
            "human_verification_required": True,
            "status": "insufficient_reports",
        }

    if len(cleaned_reports) > 10:
        raise ValueError("A maximum of 10 reports can be compared.")

    for index, report in enumerate(cleaned_reports, start=1):
        if len(report) < 10:
            raise ValueError(
                f"Report {index} must contain at least 10 characters."
            )
        if len(report) > 5000:
            raise ValueError(
                f"Report {index} must not exceed 5000 characters."
            )

    api_key = os.getenv("NEBIUS_API_KEY")

    if not api_key:
        raise RuntimeError(
            "NEBIUS_API_KEY is not set. Set it in the same terminal "
            "where you start the FastAPI server."
        )

    client = OpenAI(
        base_url="https://api.tokenfactory.nebius.com/v1/",
        api_key=api_key,
        timeout=90.0,
        max_retries=2,
    )

    numbered_reports = "\n\n".join(
        f"REPORT {index}:\n{report}"
        for index, report in enumerate(cleaned_reports, start=1)
    )

    user_prompt = f"""
Compare the following emergency reports.

{numbered_reports}

Return the required JSON object. Keep the output concise.
"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1600,
            temperature=0.1,
        )
    except Exception as exc:
        logging.exception("Nebius verification request failed")
        raise RuntimeError(
            f"Could not get a verification response from Nebius: {exc}"
        ) from exc

    if not response.choices:
        raise RuntimeError("The verification model returned no choices.")

    choice = response.choices[0]
    raw = choice.message.content
    finish_reason = choice.finish_reason

    if not raw or not raw.strip():
        logging.error(
            "Empty verification response. finish_reason=%s, usage=%s",
            finish_reason,
            response.usage,
        )

        raise RuntimeError(
            "Verification model returned no visible output. "
            f"Finish reason: {finish_reason}. "
            "The response may have exhausted its token budget. "
            "Check the backend terminal for the logged usage details."
        )

    result = _extract_json(raw)

    # Validate and normalize the response fields.
    for field in (
        "verified_facts",
        "conflicting_information",
        "unknown_information",
    ):
        if not isinstance(result.get(field), list):
            result[field] = []

    try:
        confidence = int(result.get("confidence_score", 0))
    except (TypeError, ValueError):
        confidence = 0

    result["confidence_score"] = max(0, min(100, confidence))
    result["human_verification_required"] = True
    result["status"] = "analyzed"

    return result
