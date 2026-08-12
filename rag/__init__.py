"""DIU knowledge-base construction and retrieval primitives.

Heavy optional dependencies (sentence-transformers, psycopg, and pgvector) are
loaded only when their production implementations are instantiated.  Importing
this package therefore remains safe for data validation and unit tests.
"""

from rag.models import IndexReport, KnowledgeChunk, SearchResult

__all__ = ["IndexReport", "KnowledgeChunk", "SearchResult"]
