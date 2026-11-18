"""Deterministic synthetic evaluation corpus generator (outside the runtime package)."""

from .generate import CorpusSpec, generate_corpus, write_corpus

__all__ = ["CorpusSpec", "generate_corpus", "write_corpus"]
