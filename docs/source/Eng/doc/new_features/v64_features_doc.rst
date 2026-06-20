Full-Text Search (BM25)
=======================

``fuzzy`` does pairwise string similarity and ``skill_library`` does
alphabetical substring matching, but neither ranks a *corpus* of documents by
relevance — a rare distinctive term and a ubiquitous one weigh the same. This
adds an inverted-index search that ranks documents with Okapi **BM25** (or
TF-IDF), so flows and agents can search logs, scraped records, or knowledge
snippets without a database.

Pure standard library (``math`` + ``collections`` + ``re``); deterministic;
imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import SearchIndex, search_documents

    corpus = {
        "d1": "the quick brown fox jumps over the lazy dog",
        "d2": "a quick brown dog runs fast",
        "d3": "the database stores quick query results",
    }

    index = SearchIndex.build(corpus)          # or SearchIndex(); index.add(id, text)
    for hit in index.search("quick dog", top_k=5):
        print(hit.doc_id, hit.score)

    # one-shot convenience
    hits = search_documents(corpus, "database", mode="bm25")

``SearchIndex.add`` / ``remove`` keep the index up to date incrementally;
``build`` indexes a ``{doc_id: text}`` map (or ``(id, text)`` pairs). ``search``
returns ranked ``SearchHit(doc_id, score)`` results — by default BM25
(``k1=1.5``, ``b=0.75``), or ``mode="tfidf"``. The scoring is the standard
Okapi formula with ``IDF = ln(1 + (N − df + 0.5) / (df + 0.5))``, so a rare term
out-ranks a common one, term-frequency saturates (``k1``), and long documents
are normalized down (``b``). A ``stop_words`` set can be supplied to drop noise
terms. Results are deterministic (ties broken by ``doc_id``).

Executor command
----------------

``AC_search_documents`` takes ``docs`` (a ``{doc_id: text}`` map or JSON
string), a ``query``, and optional ``top_k`` / ``mode``; it returns
``{hits: [{doc_id, score}]}``. The same operation is exposed as the MCP tool
``ac_search_documents`` and as a Script Builder command under **Data**.
