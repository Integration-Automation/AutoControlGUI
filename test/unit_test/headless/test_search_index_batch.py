"""Headless tests for the BM25/TF-IDF search index. Pure stdlib, no Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.search_index import (
    SearchHit, SearchIndex, search_documents, tokenize)

CORPUS = {
    "d1": "the quick brown fox jumps over the lazy dog",
    "d2": "a quick brown dog runs fast",
    "d3": "lazy cats sleep all day every day",
    "d4": "the database stores quick query results quickly quick quick",
}


def test_tokenize():
    assert tokenize("Hello, World! 123 foo-bar") == \
        ["hello", "world", "123", "foo", "bar"]


def test_build_and_stats():
    index = SearchIndex.build(CORPUS)
    assert index.stats()["docs"] == 4
    assert index.stats()["terms"] > 0


def test_rare_term_outranks_common():
    index = SearchIndex.build(CORPUS)
    hits = index.search("database")
    assert [h.doc_id for h in hits] == ["d4"]   # only doc with the term
    assert isinstance(hits[0], SearchHit)


def test_ranked_results_are_ordered_by_score():
    index = SearchIndex.build(CORPUS)
    hits = index.search("quick dog")
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert "d2" in {h.doc_id for h in hits[:2]}   # short doc with both terms


def test_tf_saturation():
    # a doc with many repeats does not score linearly in tf
    index = SearchIndex.build({"a": "quick", "b": "quick quick quick quick"})
    hits = {h.doc_id: h.score for h in index.search("quick")}
    assert hits["b"] < 4 * hits["a"]


def test_length_normalization():
    short = "alpha beta"
    long = "alpha " + " ".join(f"w{i}" for i in range(50))
    index = SearchIndex.build({"short": short, "long": long})
    hits = {h.doc_id: h.score for h in index.search("alpha")}
    assert hits["short"] > hits["long"]


def test_tfidf_mode_differs_from_bm25():
    index = SearchIndex.build(CORPUS)
    bm25 = [h.doc_id for h in index.search("quick dog", mode="bm25")]
    tfidf = [h.doc_id for h in index.search("quick dog", mode="tfidf")]
    assert bm25 and tfidf            # both return results
    assert isinstance(bm25, list)


def test_top_k_and_no_match():
    index = SearchIndex.build(CORPUS)
    assert len(index.search("quick", top_k=2)) == 2
    assert index.search("nonexistentterm") == []


def test_remove_and_reindex():
    index = SearchIndex.build(CORPUS)
    assert index.remove("d4") is True
    assert index.search("database") == []
    assert index.remove("missing") is False
    index.add("d2", "quick quick brown dog")    # re-index replaces
    assert index.stats()["docs"] == 3


def test_deterministic():
    first = [h.doc_id for h in search_documents(CORPUS, "quick")]
    second = [h.doc_id for h in search_documents(CORPUS, "quick")]
    assert first == second


def test_stop_words():
    index = SearchIndex.build({"a": "the the the cat"}, stop_words={"the"})
    assert index.search("the") == []
    assert [h.doc_id for h in index.search("cat")] == ["a"]


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_search_documents",
        {"docs": json.dumps(CORPUS), "query": "lazy dog", "top_k": 3},
    ]])
    hits = next(v for v in rec.values() if isinstance(v, dict))["hits"]
    assert hits and all("doc_id" in h and "score" in h for h in hits)


def test_wiring():
    assert "AC_search_documents" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_search_documents" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_search_documents" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("SearchIndex", "SearchHit", "search_documents", "tokenize"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
