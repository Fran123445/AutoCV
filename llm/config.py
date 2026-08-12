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

SEEDS_DIR = Path(__file__).parents[1] / "seeds"
