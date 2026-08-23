"""In-memory full-text search with BM25 / TF-IDF ranking.

``fuzzy`` does pairwise string similarity and ``skill_library`` does
alphabetical substring matching, but neither ranks a *corpus* of documents by
relevance — a rare distinctive term and a ubiquitous one weigh the same. This
adds an inverted-index search that ranks documents with Okapi BM25 (or TF-IDF),
so flows and agents can search logs, scraped records, or knowledge snippets
without a database.

Pure standard library (``math`` + ``collections`` + ``re``); deterministic;
imports no ``PySide6``.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import (
    Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

Docs = Union[Dict[str, str], Iterable[Tuple[str, str]]]


@dataclass(frozen=True)
class SearchHit:
    """One ranked search result."""

    doc_id: str
    score: float


def tokenize(text: str) -> List[str]:
    """Lower-case and split ``text`` into alphanumeric terms."""
    return _TOKEN_RE.findall(str(text).lower())


class SearchIndex:
    """An inverted index over documents, ranked by BM25 or TF-IDF."""

    def __init__(self, *, k1: float = 1.5, b: float = 0.75,
                 stop_words: Optional[Iterable[str]] = None) -> None:
        self._k1 = float(k1)
        self._b = float(b)
        self._stop = set(stop_words or ())
        self._postings: Dict[str, Dict[str, int]] = {}
        self._doc_len: Dict[str, int] = {}

    def _terms(self, text: str) -> List[str]:
        return [term for term in tokenize(text) if term not in self._stop]

    def add(self, doc_id: str, text: str) -> None:
        """Index ``text`` under ``doc_id`` (re-indexing replaces the old text)."""
        self.remove(doc_id)
        terms = self._terms(text)
        self._doc_len[doc_id] = len(terms)
        for term, freq in Counter(terms).items():
            self._postings.setdefault(term, {})[doc_id] = freq

    def remove(self, doc_id: str) -> bool:
        """Drop ``doc_id`` from the index; return whether it was present."""
        if doc_id not in self._doc_len:
            return False
        del self._doc_len[doc_id]
        for postings in self._postings.values():
            postings.pop(doc_id, None)
        for term in [t for t, p in self._postings.items() if not p]:
            del self._postings[term]
        return True

    @classmethod
    def build(cls, docs: Docs, **kwargs) -> "SearchIndex":
        """Build an index from a ``{doc_id: text}`` map or ``(id, text)`` pairs."""
        index = cls(**kwargs)
        items = docs.items() if isinstance(docs, dict) else docs
        for doc_id, text in items:
            index.add(doc_id, text)
        return index

    def stats(self) -> Dict[str, int]:
        """Return ``{docs, terms}`` counts."""
        return {"docs": len(self._doc_len), "terms": len(self._postings)}

    def _avgdl(self) -> float:
        if not self._doc_len:
            return 1.0
        return sum(self._doc_len.values()) / len(self._doc_len)

    def _idf(self, term: str) -> float:
        total = len(self._doc_len)
        df = len(self._postings.get(term, {}))
        return math.log(1 + (total - df + 0.5) / (df + 0.5))

    def _bm25(self, terms: Sequence[str], doc_id: str, avgdl: float) -> float:
        score = 0.0
        norm = 1 - self._b + self._b * self._doc_len[doc_id] / avgdl
        for term in terms:
            freq = self._postings.get(term, {}).get(doc_id)
            if not freq:
                continue
            score += self._idf(term) * (freq * (self._k1 + 1)) / (
                freq + self._k1 * norm)
        return score

    def _tfidf(self, terms: Sequence[str], doc_id: str, _avgdl: float) -> float:
        total = len(self._doc_len)
        score = 0.0
        for term in terms:
            postings = self._postings.get(term, {})
            freq = postings.get(doc_id)
            if not freq:
                continue
            score += (1 + math.log(freq)) * math.log(total / len(postings))
        return score

    def search(self, query: str, *, top_k: int = 10,
               mode: str = "bm25") -> List[SearchHit]:
        """Return up to ``top_k`` documents ranked for ``query``."""
        terms = self._terms(query)
        candidates: Set[str] = set()
        for term in terms:
            candidates.update(self._postings.get(term, {}))
        avgdl = self._avgdl()
        scorer = self._tfidf if mode == "tfidf" else self._bm25
        ranked = ((doc_id, scorer(terms, doc_id, avgdl)) for doc_id in candidates)
        hits = [(doc_id, score) for doc_id, score in ranked if score > 0]
        hits.sort(key=lambda item: (-item[1], item[0]))
        return [SearchHit(doc_id=doc_id, score=round(score, 6))
                for doc_id, score in hits[:top_k]]


def search_documents(docs: Docs, query: str, *, top_k: int = 10,
                     mode: str = "bm25") -> List[SearchHit]:
    """One-shot: build an index over ``docs`` and search it for ``query``."""
    return SearchIndex.build(docs).search(query, top_k=top_k, mode=mode)
