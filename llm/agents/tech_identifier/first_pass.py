import httpx
from pydantic import BaseModel, Field
import json
from pathlib import Path
from typing import Literal


ENDPOINT = "http://localhost:5001/v1/chat/completions"
TIMEOUT = 300.0
# Gemma degenerates under greedy decoding, so sampling stays on.
TEMPERATURE = 0.95

SEEDS_PATH = Path(__file__).parents[3] / "seeds" / "technologies.json"


def _load_registry() -> list[dict]:
    """
    Load the technology registry
    """
    with open(SEEDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["technologies"]


REGISTRY = _load_registry()
TECHNOLOGY_NAMES = [tech["name"] for tech in REGISTRY]

# Constrained decoding turns this into a grammar, so a name outside the
# registry becomes unrepresentable rather than merely discouraged.
TechnologyName = Literal[tuple(TECHNOLOGY_NAMES)]


# Instructions come first and the description is fenced, so the model can tell
# the two apart: job postings are themselves full of imperative sentences.
PROMPT_TEMPLATE = """You are a technology identifier. Read the job description delimited below and report the technologies it mentions.

Rules:
- Use only names from the allowed list. Never invent one and never reword one.
- required_technologies: what the posting demands. Anything listed under requirements, or phrased as required, mandatory, "must have", "solid knowledge of", "conocimiento solido", "experiencia en".
- nice_to_have_technologies: what the posting treats as optional or advantageous: "deseable", "nice to have", "a plus", "preferred", "bonus", "valorable", "no excluyente".
- min_experience and max_experience: years demanded for that specific technology, and only when the description states them. Use null when it says nothing. A general figure such as "2+ years of experience" belongs to the role rather than to any one technology, so do not copy it onto every entry.
- discarded_technologies: technologies or tools named in the description that have no match in the allowed list.
- Ignore anything that appears only in benefits, perks or company boilerplate. Report what the role actually uses or requires.

Allowed technologies:
{tech_list}

<job_description>
{job_desc}
</job_description>
"""


class Technology(BaseModel):
    name: TechnologyName = Field(
        description="The name of the technology, taken verbatim from the allowed list."
    )
    min_experience: int | None = Field(
        default=None,
        description="Years of experience required for this specific technology. Null when the job description does not state it.",
    )
    max_experience: int | None = Field(
        default=None,
        description="Upper bound of years for this specific technology. Null when the job description does not state it, meaning there is no upper limit.",
    )


class TechnologyList(BaseModel):
    required_technologies: list[Technology] = Field(
        description="The technologies the job description demands."
    )
    nice_to_have_technologies: list[Technology] = Field(
        description="The technologies the job description treats as desirable rather than required."
    )
    discarded_technologies: list[str] = Field(
        description="Technologies mentioned in the job description but not available as an option."
    )


def post_chat(prompt: str, schema: dict) -> dict:
    """
    Send a prompt to the local model and return the parsed JSON content.

    Args:
        prompt (str): The full prompt to send.
        schema (dict): JSON schema constraining the reply.
    """
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object", "schema": schema},
        "temperature": TEMPERATURE,
    }

    with httpx.Client() as client:
        response = client.post(ENDPOINT, json=payload, timeout=TIMEOUT)

    try:
        return json.loads(response.json()["choices"][0]["message"]["content"])
    except Exception as e:
        raise ValueError(
            f"Failed to parse response: {e}. Response content: {response.text}"
        )


def run_first_pass(job_desc: str) -> TechnologyList:
    """
    Identify technologies mentioned in a job description.

    Args:
        job_desc (str): The job description text.
    """
    prompt = PROMPT_TEMPLATE.format(
        tech_list=", ".join(TECHNOLOGY_NAMES),
        job_desc=job_desc,
    )

    return TechnologyList.model_validate(
        post_chat(prompt, TechnologyList.model_json_schema())
    )
