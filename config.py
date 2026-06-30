"""Shared configuration for Lab 24: Eval + Guardrail Stack."""

import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
HF_TOKEN = os.getenv("HF_TOKEN", "")  # Optional: for HuggingFace models

# --- LLM provider (hỗ trợ OpenAI gốc HOẶC OpenRouter) ---
# OpenRouter: đặt OPENAI_BASE_URL=https://openrouter.ai/api/v1 và model dạng "openai/gpt-4o-mini"
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "") or os.getenv("OPENAI_API_BASE", "")
# Nếu dùng OpenRouter, client SDK đọc OPENAI_BASE_URL tự động. Đồng bộ ngược lại để chắc chắn.
if OPENAI_BASE_URL:
    os.environ.setdefault("OPENAI_BASE_URL", OPENAI_BASE_URL)
    os.environ.setdefault("OPENAI_API_BASE", OPENAI_BASE_URL)

# Model dùng để SINH answer (setup_answers.py) — cho phép override qua env LLM_MODEL.
GEN_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# --- Qdrant (same as Day 18) ---
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "lab24_production"

# --- Embedding (same as Day 18) ---
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024

# --- Chunking (same as Day 18) ---
HIERARCHICAL_PARENT_SIZE = 2048
HIERARCHICAL_CHILD_SIZE = 256
SEMANTIC_THRESHOLD = 0.85

# --- Search (same as Day 18) ---
BM25_TOP_K = 20
DENSE_TOP_K = 20
HYBRID_TOP_K = 20
RERANK_TOP_K = 3

# --- Paths ---
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TEST_SET_PATH = os.path.join(os.path.dirname(__file__), "test_set_50q.json")
ANSWERS_PATH = os.path.join(os.path.dirname(__file__), "answers_50q.json")
HUMAN_LABELS_PATH = os.path.join(os.path.dirname(__file__), "human_labels_10q.json")
ADVERSARIAL_SET_PATH = os.path.join(os.path.dirname(__file__), "adversarial_set_20.json")
GUARDRAILS_CONFIG_DIR = os.path.join(os.path.dirname(__file__), "guardrails")

# --- LLM Judge ---
JUDGE_MODEL = os.getenv("JUDGE_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini"))

# --- Guardrail latency budget ---
LATENCY_BUDGET_P95_MS = 500  # target: full guard stack P95 < 500ms
PRESIDIO_LANGUAGE = "en"    # Presidio base language; custom VN recognizers added via PatternRecognizer
