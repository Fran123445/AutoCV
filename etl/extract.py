
def _clean_html(html_content: str) -> str:
    """
    Cleans the HTML content by removing unnecessary tags and whitespace.

    Args:
        html_content (str): The raw HTML content.
    """
    pass

def _extract_header(cleaned_html: str) -> dict:
    """
    Extracts the header information from the cleaned HTML content.

    Args:
        cleaned_html (str): The cleaned HTML content.
    """
    pass

def _extract_body(cleaned_html: str) -> str:
    """
    Extracts the body content from the cleaned HTML content.

    Args:
        cleaned_html (str): The cleaned HTML content.
    """
    pass

def extract_from_html(html_content: str):
    cleaned_html = _clean_html(html_content)
    header = _extract_header(cleaned_html)
    body = _extract_body(cleaned_html)

    return {
        "header": header,
        "body": body
    }