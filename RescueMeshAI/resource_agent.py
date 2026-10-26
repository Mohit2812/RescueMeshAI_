
import os
import json
import re
from openai import OpenAI

MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"

DEFAULT_INVENTORY = [
    {"resource": "Rescue Team", "quantity": 1},
    {"resource": "Ambulance", "quantity": 1},
    {"resource": "Medical Team", "quantity": 1},
    {"resource": "Drone", "quantity": 1},
    {"resource": "Structural Engineer", "quantity": 0},
    {"resource": "Traffic Support Unit", "quantity": 1},
]

SYSTEM_PROMPT = """
You are the RescueMesh AI Resource Allocation Agent.
Estimate resources needed using only supplied information and inventory.
Do not claim that a resource has been dispatched or is available in real time.
Quantities are planning estimates and must be reviewed by a human.
Return only valid JSON:
{
  "required_resources": [
    {"resource": "", "quantity": 0, "reason": ""}
  ],
  "available_resources": [
    {"resource": "", "quantity": 0}
  ],
  "resource_gaps": [
    {"resource": "", "missing_quantity": 0}
  ],
  "warnings": [],
  "human_approval_required": true
}
"""


def allocate_resources(
    incident: dict,
    priority: dict,
    inventory: list[dict] | None = None,
) -> dict:
    api_key = os.getenv("NEBIUS_API_KEY")
    if not api_key:
        raise RuntimeError("NEBIUS_API_KEY is not set.")

    client = OpenAI(
        base_url="https://api.tokenfactory.nebius.com/v1/",
        api_key=api_key,
        timeout=90.0,
        max_retries=2,
    )

    payload = {
        "incident_analysis": incident,
        "priority_assessment": priority,
        "inventory": inventory if inventory is not None else DEFAULT_INVENTORY,
    }

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ],
        max_tokens=1800,
        temperature=0.1,
    )

    raw = response.choices[0].message.content
    if not raw:
        raise RuntimeError(
            "Resource agent returned empty output. "
            f"Finish reason: {response.choices[0].finish_reason}"
        )

    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)

    result = json.loads(raw)
    result["human_approval_required"] = True
    return result
