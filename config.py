"""Shared configuration: environment variables, model names, Pinecone access.

Everything here fails loudly and early, so a fresh clone with an unconfigured
.env gets a message that says what to do rather than a traceback from inside a
client library.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# The embedding model fixes the dimension the Pinecone index must have.
REASONING_MODEL = "gpt-4o"
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSION = 3072
EMBEDDING_METRIC = "cosine"

_VARIABLE_HELP = {
    "TELEGRAM_BOT_TOKEN": "a bot token from @BotFather (https://t.me/botfather)",
    "OPENAI_API_KEY": "an OpenAI API key (https://platform.openai.com/api-keys)",
    "PINECONE_API_KEY": "a Pinecone API key (https://app.pinecone.io)",
    "PINECONE_INDEX_NAME": (
        f"the name of a Pinecone index with dimension {EMBEDDING_DIMENSION} "
        f"and the {EMBEDDING_METRIC} metric"
    ),
}


class ConfigError(Exception):
    """The environment is not usable. The message says how to fix it."""


def require(*names):
    """Raise ConfigError if any named variable is unset or still holds its
    .env.example placeholder."""
    missing = []
    for name in names:
        value = (os.getenv(name) or "").strip()
        if not value or value.startswith("your_"):
            missing.append(f"  {name} - {_VARIABLE_HELP[name]}")

    if missing:
        raise ConfigError(
            "Missing configuration:\n\n"
            + "\n".join(missing)
            + "\n\nCopy .env.example to .env and fill these in:\n"
            "  cp .env.example .env"
        )


def get(name):
    """Read a required variable, validating it first."""
    require(name)
    return os.getenv(name).strip()


def openai_client():
    """Build an OpenAI client from the environment."""
    import openai

    return openai.OpenAI(api_key=get("OPENAI_API_KEY"))


def pinecone_index(require_populated=False):
    """Open the configured Pinecone index.

    Checks up front that the index exists and matches the embedding model, and
    optionally that the law has already been ingested into it.
    """
    import pinecone

    api_key = get("PINECONE_API_KEY")
    name = get("PINECONE_INDEX_NAME")
    pc = pinecone.Pinecone(api_key=api_key)

    try:
        description = pc.describe_index(name)
    except Exception as error:
        raise ConfigError(
            f"Cannot open Pinecone index '{name}': {error}\n\n"
            f"Create it at https://app.pinecone.io with dimension "
            f"{EMBEDDING_DIMENSION} and the {EMBEDDING_METRIC} metric, then set "
            f"PINECONE_INDEX_NAME to its name.{_available_indexes_hint(pc)}"
        ) from error

    if description.dimension != EMBEDDING_DIMENSION:
        raise ConfigError(
            f"Pinecone index '{name}' has dimension {description.dimension}, but "
            f"{EMBEDDING_MODEL} produces {EMBEDDING_DIMENSION}-dimensional "
            f"vectors.\n\nCreate an index with dimension {EMBEDDING_DIMENSION} "
            f"and the {EMBEDDING_METRIC} metric, then ingest the law into it:\n"
            "  python scraper.py"
        )

    index = pc.Index(name)

    if require_populated and _vector_count(index) == 0:
        raise ConfigError(
            f"Pinecone index '{name}' is empty, so there is no law to retrieve "
            "and every answer would be meaningless.\n\n"
            "Ingest the law first (this is a one-time step):\n"
            "  python scraper.py"
        )

    return index


def _vector_count(index):
    try:
        stats = index.describe_index_stats()
    except Exception:
        return -1  # Unknown: do not block startup on a stats call.
    return getattr(stats, "total_vector_count", None) or 0


def _available_indexes_hint(pc):
    try:
        names = pc.list_indexes().names()
    except Exception:
        return ""
    if not names:
        return "\n\nThis API key currently has no indexes."
    return "\n\nIndexes available to this API key: " + ", ".join(names)
