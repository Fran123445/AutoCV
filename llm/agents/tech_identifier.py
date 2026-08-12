import httpx
from pydantic import BaseModel, Field
import json
from pathlib import Path
from typing import Literal


def _load_tech_list() -> list[str]:
    """
    Load the list of technologies
    """
    with open(Path(__file__).parent.parent.parent / "seeds" / "technologies.json", "r", encoding="utf-8") as f:
        tech_dict = json.load(f)

    return [tech["name"] for tech in tech_dict["technologies"]]


TECHNOLOGY_NAMES = _load_tech_list()

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

tech_list_json = TechnologyList.model_json_schema()

def _parse_reponse(response: httpx.Response) -> TechnologyList:
    """
    Parse the response from the LLM and return a TechnologyList object.
    """
    try:
        response_json = response.json()
        content = response_json["choices"][0]["message"]["content"]
        return TechnologyList.model_validate_json(content)
    except Exception as e:
        raise ValueError(f"Failed to parse response: {e}. Response content: {response.text}")

def identify_technologies(job_desc: str):
    """
    Identify technologies mentioned in a job description.

    Args:
        job_desc (str): The job description text.
    """

    prompt = PROMPT_TEMPLATE.format(tech_list=", ".join(TECHNOLOGY_NAMES),
                                job_desc=job_desc)

    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object", "schema": tech_list_json},
        # Extraction, not authoring: the same posting must map to the same JSON.
        "temperature": 0.95,
    }

    with httpx.Client() as client:
        response = client.post(
            "http://localhost:5001/v1/chat/completions",
            json=payload,
            timeout=300.0,
        )

        return _parse_reponse(response)
