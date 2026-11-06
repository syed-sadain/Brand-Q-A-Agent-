"""Verify that the local environment can run the Brand Q&A agent.

This script performs a set of non-destructive checks and prints a PASS/FAIL
report. It needs no API key and makes no network calls.

Checks performed:

1. The Python interpreter is version 3.11 or newer.
2. Every required third-party package is importable.
3. Optional packages are importable (reported but never fatal).
4. :class:`app.core.config.Settings` loads and reports its effective values,
   including whether an LLM API key is configured (the key value itself is
   never printed).

The process exits with code ``0`` when all required checks pass and ``1``
otherwise.

Usage::

    .venv\\Scripts\\python.exe scripts\\verify_environment.py
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Make ``import app...`` work regardless of the current working directory.
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MIN_PYTHON: tuple[int, int] = (3, 11)

REQUIRED_PACKAGES: tuple[str, ...] = (
    "fastapi",
    "pydantic",
    "pydantic_settings",
    "httpx",
    "bs4",
    "lxml",
    "langchain_core",
    "langchain_text_splitters",
    "langgraph",
)

OPTIONAL_PACKAGES: tuple[str, ...] = (
    "pinecone",
    "chromadb",
    "langchain_openai",
    "langchain_anthropic",
    "langchain_google_genai",
)


def check_python_version() -> bool:
    """Check that the running interpreter is at least Python 3.11."""
    detected = ".".join(str(part) for part in sys.version_info[:3])
    ok = sys.version_info[:2] >= MIN_PYTHON
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] Python version: {detected} (required >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]})")
    return ok


def check_packages(names: tuple[str, ...], *, optional: bool) -> bool:
    """Try importing each package and report OK / FAIL / optional-missing.

    Returns ``True`` when no *required* package is missing.
    """
    all_ok = True
    label = "optional" if optional else "required"
    for name in names:
        try:
            importlib.import_module(name)
            print(f"[ OK ] {label} package: {name}")
        except Exception as exc:
            if optional:
                print(f"[ -- ] optional package missing: {name} ({type(exc).__name__})")
            else:
                print(f"[FAIL] required package missing: {name} ({type(exc).__name__})")
                all_ok = False
    return all_ok


def check_settings() -> bool:
    """Load application settings and report effective values.

    Reports whether an LLM API key is configured without ever printing the key.
    Returns ``True`` when settings load successfully.
    """
    try:
        from app.core.config import Settings

        settings = Settings()
    except Exception as exc:
        print(f"[FAIL] Settings could not be loaded ({type(exc).__name__}: {exc})")
        return False

    print("[PASS] Settings loaded:")
    print(f"         vector_store_provider = {settings.vector_store_provider}")
    print(f"         llm_provider          = {settings.llm_provider}")
    print(f"         embedding_provider    = {settings.embedding_provider}")
    print(f"         chunk_size            = {settings.chunk_size}")
    print(f"         chunk_overlap         = {settings.chunk_overlap}")
    print(f"         retrieval_top_k       = {settings.retrieval_top_k}")

    key_configured = bool(settings.resolved_llm_api_key())
    print(
        f"         LLM API key           = {'configured' if key_configured else 'not configured'}"
    )
    return True


def main() -> int:
    """Run all checks and print a final summary. Returns the exit code."""
    print("Brand Q&A agent — environment verification")
    print("=" * 60)

    required_ok = True
    required_ok = check_python_version() and required_ok

    print("-" * 60)
    print("Required packages")
    required_ok = check_packages(REQUIRED_PACKAGES, optional=False) and required_ok

    print("-" * 60)
    print("Optional packages (missing is acceptable)")
    check_packages(OPTIONAL_PACKAGES, optional=True)

    print("-" * 60)
    settings_ok = check_settings()
    required_ok = settings_ok and required_ok

    print("-" * 60)
    if required_ok:
        print("RESULT: PASS — all required checks succeeded.")
        return 0

    print("RESULT: FAIL — one or more required checks failed (see above).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
