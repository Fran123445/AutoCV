# JD transform test set

```
extracted_jds_input/       23  input:    output of etl/jobs/extract.py
expected_transform_output/ 23  expected: output of etl/jobs/transform.py
```

Filenames match 1:1. `header` and `body` are carried through unchanged, so compare only
`technologies`, `concepts`, `seniority`, `role`, `degree`.

## Run

Expected output is model output, produced by running `etl/jobs/transform.py` over the inputs here.

| | |
|---|---|
| Model | `openai/gpt-5.6-luna-pro` (OpenRouter) |
| Temperature | 0.2 |
| Timeout | 300s |
| Max concurrency | 4 |
| Git commit | `6d8f58b` |
| Tokens | 3,353,601 prompt / 254,262 completion / 194,394 reasoning |

7 calls per posting:

| Task | Passes | Reasoning |
|---|---|---|
| `tech_identifier` | first + second | on |
| `concept_identifier` | first + second | on |
| `seniority_identifier` | classify | off |
| `role_identifier` | classify | off |
| `degree_identifier` | classify | off |

`llm/client.py` sends `reasoning: {"effort": "medium"}` while the `-pro` slug selects max effort;
which governed is not recoverable from the response.

## Vocabulary

All names come from `seeds/`, injected into the prompts as the allowed list: 768 technologies,
441 concepts, 32 roles, 5 seniority labels, 14 degrees. `discarded_*` holds terms no seed entry
matched. Changing `seeds/` invalidates this expected output. Regenerate in the same commit.
