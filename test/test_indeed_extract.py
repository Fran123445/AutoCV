from etl.jobs.extract import extract_from_file, extractor_for
from etl.jobs.extract.indeed import extract


def make_page(
    source_url="https://ar.indeed.com/viewjob?jk=abc123",
    title="Data Engineer",
    company="Acme",
    location="Buenos Aires, Buenos Aires",
    contract_type="Tiempo completo",
    body="Buscamos un ingeniero de datos. " * 30,
):
    return f"""
    <html>
      <head>
        <meta property="og:url" content="{source_url}&from=social_other">
      </head>
      <body>
        <h1 data-testid="jobsearch-JobInfoHeader-title">{title}</h1>
        <div data-testid="inlineHeader-companyName">{company}</div>
        <div data-testid="inlineHeader-companyLocation">{location}</div>
        <div id="salaryInfoAndJobType">{contract_type}</div>
        <div id="jobDescriptionText">
          <p>{body}</p>
          <ul><li>Python</li><li>SQL</li></ul>
        </div>
      </body>
    </html>
    """


def test_dispatcher_selects_indeed():
    assert extractor_for("https://ar.indeed.com/viewjob?jk=abc123").extract is extract


def test_extract_reads_stable_indeed_fields():
    result = extract(
        make_page(),
        {"source_url": "https://ar.indeed.com/viewjob?jk=abc123&from=serp"},
    )

    assert result["header"] == {
        "source": "indeed",
        "source_url": "https://ar.indeed.com/viewjob?jk=abc123",
        "indeed_job_id": "abc123",
        "position_name": "Data Engineer",
        "company_name": "Acme",
        "location": "Buenos Aires, Buenos Aires",
        "modality": None,
        "contract_type": "Tiempo completo",
        "posted_raw": None,
        "posted_days_ago": None,
    }
    assert "Python" in result["body"]
    assert "\n" in result["body"]


def test_file_extract_dispatches_indeed(tmp_path):
    path = tmp_path / "posting.html"
    saved_comment = (
        "<!-- saved from url=(0045)"
        "https://ar.indeed.com/viewjob?jk=abc123 -->"
    )
    path.write_text(saved_comment + make_page(), encoding="utf-8")

    result = extract_from_file(path)

    assert result["header"]["source"] == "indeed"
    assert result["header"]["indeed_job_id"] == "abc123"
    assert result["header"]["position_name"] == "Data Engineer"
