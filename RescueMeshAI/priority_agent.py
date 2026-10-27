
import os
import json
import re
from openai import OpenAI


SYSTEM_PROMPT = """
You are the RescueMesh AI Priority Assessment Agent.

Assess emergency priority using only the incident information provided.
Do not invent facts. Treat uncertainty explicitly.
Do not provide hidden reasoning. Return only a JSON object.

Use this exact schema:
{
  "priority": "critical|high|medium|low|unknown",
  "severity": "critical|high|medium|low|unknown",
  "people_at_risk": "string",
  "medical_urgency": "critical|high|medium|low|unknown",
  "access_difficulty": "severe|high|moderate|low|unknown",
  "time_sensitivity": "immediate|urgent|normal|unknown",
  "confidence": 0,
  "human_review_required": true
}

Confidence must be an integer from 0 to 100.
Always set human_review_required to true.
"""


def assess_priority(incident_data):
    """Assess incident priority using the Nebius-hosted model."""

    api_key = os.getenv("NEBIUS_API_KEY")

    if not api_key:
        raise RuntimeError(
            "NEBIUS_API_KEY is not set in the backend environment."
        )

    client = OpenAI(
        base_url="https://api.tokenfactory.nebius.com/v1/",
        api_key=api_key,
    )

    response = client.chat.completions.create(
        model="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": str(incident_data)},
        ],
        max_tokens=2700,
    )

    message = response.choices[0].message
    raw = message.content

    if not raw or not raw.strip():
        raise RuntimeError(
            "Priority model returned no visible output. "
            f"Finish reason: {response.choices[0].finish_reason}"
        )

    raw = raw.strip()

    # Handle models that wrap JSON in Markdown fences.
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Priority model returned invalid JSON: {raw[:300]}"
        ) from error

    allowed = {
        "critical", "high", "medium", "low", "unknown"
    }

    if result.get("priority") not in allowed:
        raise RuntimeError("Priority model returned an invalid priority.")

    confidence = result.get("confidence")

    if (
        not isinstance(confidence, int)
        or isinstance(confidence, bool)
        or not 0 <= confidence <= 100
    ):
        raise RuntimeError("Priority confidence must be an integer from 0 to 100.")

    result["human_review_required"] = True

    return result 