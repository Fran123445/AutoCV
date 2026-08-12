import json

from llm.config import SEEDS_DIR


def load_seed(filename: str, key: str) -> list[dict]:
    """
    Load a seed registry from disk.

    Args:
        filename (str): File under seeds/, extension included.
        key (str): Key holding the entry list inside that file.
    """
    with open(SEEDS_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)[key]


def render_names(entries: list[dict]) -> str:
    """
    Render a registry as a plain comma-separated list of canonical names.

    Args:
        entries (list[dict]): Registry entries, each carrying a "name".
    """
    return ", ".join(entry["name"] for entry in entries)


def render_with_aliases(entries: list[dict]) -> str:
    """
    Render a registry as "canonical (alias, alias)" entries.

    Args:
        entries (list[dict]): Registry entries, each carrying a "name" and an
            "aliases" list.
    """
    rendered = []
    for entry in entries:
        if entry["aliases"]:
            rendered.append(f"{entry['name']} ({', '.join(entry['aliases'])})")
        else:
            rendered.append(entry["name"])

    return ", ".join(rendered)
