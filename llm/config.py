from pathlib import Path


BASE_URL = "http://localhost:5001"
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

# Empty while the server is local and unauthenticated. The client only sends
# either one once it is filled in.
API_KEY = ""
MODEL_NAME = ""

TIMEOUT = 300.0
# Gemma degenerates under greedy decoding, so sampling stays on.
TEMPERATURE = 0.95

# Postings transformed at once. Locally this should match llama-server's
# --parallel slot count: past that the extra requests only queue, and the
# server splits its KV cache across the slots, so each one holds less context.
# Raise it once BASE_URL points somewhere hosted.
MAX_CONCURRENCY = 4

SEEDS_DIR = Path(__file__).parents[1] / "seeds"
