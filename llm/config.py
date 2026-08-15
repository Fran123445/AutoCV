from pathlib import Path

import os

from dotenv import load_dotenv


# Also called in the root config.py. Neither module imports the other, and
# whichever is imported first has to see the file.
load_dotenv(Path(__file__).parents[1] / ".env")

BASE_URL = os.getenv("AUTOCV_BASE_URL", "http://localhost:5001")
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

# Both empty while the server is local and unauthenticated. The client only
# sends either one once it is set.
API_KEY = os.getenv("AUTOCV_API_KEY", "")
MODEL_NAME = os.getenv("AUTOCV_MODEL_NAME", "")

# `or` rather than a getenv default: a variable left blank in .env arrives as an
# empty string, which is a default the caller meant, not a number.
TIMEOUT = float(os.getenv("AUTOCV_TIMEOUT") or 300)
# Gemma degenerates under greedy decoding, so sampling stays on.
TEMPERATURE = float(os.getenv("AUTOCV_TEMPERATURE") or 0.95)

# Postings transformed at once. Locally this should match llama-server's
# --parallel slot count: past that the extra requests only queue, and the
# server splits its KV cache across the slots, so each one holds less context.
# Raise it once BASE_URL points somewhere hosted.
MAX_CONCURRENCY = int(os.getenv("AUTOCV_MAX_CONCURRENCY") or 4)
