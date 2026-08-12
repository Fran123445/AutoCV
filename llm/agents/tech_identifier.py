import httpx
from pydantic import BaseModel, Field
import json
from pathlib import Path


SYSTEM_PROMPT = """
{job_desc}


You are a technology identifier. You will be given a job description and your task is to identify the technologies mentioned in it.
You should return a JSON object with two lists of technologies: one for must haves and one for nice to haves, where each technology has a name.
The technologies should be one of these:
{tech_list}

If any technology is mentioned but not available as an option, add it to the discarded list
"""

class Technology(BaseModel):
    name: str = Field(description="The name of the technology.")
    min_experienc: int = Field(description="The minimum experience required for the technology, in years.")
    max_experience: int = Field(description="The maximum experience required for the technology, in years. If not specified, it means there is no upper limit.")

class TechnologyList(BaseModel):
    required_technologies: list[Technology] = Field(
        description="The list of required technologies."
    )
    nice_to_have_technologies: list[Technology] = Field(
        description="The list of nice-to-have technologies."
    )
    discarded_technologies: list[str] = Field(
        description="Technologies mentioned in the job description but not available as an option."
    )

tech_list_json = TechnologyList.model_json_schema()

def _load_tech_list() -> list[str]:
    """
    Load the list of technologies
    """
    with open(Path(__file__).parent.parent.parent / "seeds" / "technologies.json", "r", encoding="utf-8") as f:
        tech_dict = json.load(f)

    return [tech["name"] for tech in tech_dict["technologies"]]
    
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

    tech_list = _load_tech_list()
    prompt = SYSTEM_PROMPT.format(tech_list=", ".join(tech_list), 
                                job_desc=job_desc)

    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object", "schema": tech_list_json},
        "temperature": 0.95,
    }

    with httpx.Client() as client:
        response = client.post(
            "http://localhost:5001/v1/chat/completions",
            json=payload,
            timeout=300.0,
        )

        return _parse_reponse(response)

