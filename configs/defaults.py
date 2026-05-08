# Default project settings — override via environment variables or .env

EMBEDDING_MODEL = "huyydangg/DEk21_hcmute_embedding"
EMBEDDING_DIM = 768
CHROMA_COLLECTION = "legal_chunks"
OLLAMA_MODEL = "qwen2.5:7b-instruct-q4_K_M"
OLLAMA_BASE_URL = "http://localhost:11434"
LLM_TIMEOUT = 120
LLM_TEMPERATURE = 0.1

# Hybrid matching thresholds
COSINE_HIGH = 0.85   # cosine ≥ HIGH → matched (confident same clause)
COSINE_LOW  = 0.35   # cosine < LOW  → no_match → treated as removed/added
