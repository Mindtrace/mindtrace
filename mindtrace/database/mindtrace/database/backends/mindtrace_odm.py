from abc import abstractmethod
from enum import Enum
from typing import Any, Literal, Type

from pydantic import BaseModel

from mindtrace.core import MindtraceABC


class InitMode(Enum):
    """Initialization mode for database backends."""

    SYNC = "sync"
    ASYNC = "async"


class MindtraceODM(MindtraceABC):
    """Portable ODM contract for all backends (Mongo, Redis, ...).

    Canonical query-style API
    -------------------------
    insert_one(doc)
    find(where=None, sort=None, limit=None)
    find_one(where, sort=None)
    update_one(where, set_fields, upsert=False, return_document="none")
    delete_one(where)
    delete_many(where)
    distinct(field, where=None)

    Portable filter subset (required across all backends)
    -----------------------------------------------------
    Equality:    {"field": value}
    List-as-IN:  {"field": [v1, v2, ...]}
    OR:          {"$or": [clause1, clause2, ...]}

    Any unsupported filter shape MUST raise ``QueryNotSupported``.
    Backends MUST NOT silently broaden queries (e.g. full scans).

    Legacy compatibility API (id / full-document style)
    ---------------------------------------------------
    insert, get, update, delete, all

    These remain for backward compatibility but are not the preferred
    path for new code.  Registry backends should use only canonical methods.
    """

    # ── async flag ──────────────────────────────────────────────────────

    @abstractmethod
    def is_async(self) -> bool:
        """Return True if this backend uses async operations."""

    # ── canonical query-style API ───────────────────────────────────────

    def insert_one(self, doc: BaseModel | dict):
        """Insert one document. Returns the inserted document."""
        return self.insert(doc)

    @abstractmethod
    def find(
        self,
        where: dict | None = None,
        sort: list[tuple[str, int]] | None = None,
        limit: int | None = None,
        **kwargs,
    ) -> list[BaseModel]:
        """Find documents matching a portable filter.

        Args:
            where: Portable filter dict.  Supported operators are equality,
                list-as-IN, and ``$or``.
            sort: List of ``(field, direction)`` pairs where direction is
                1 (ascending) or -1 (descending).
            limit: Maximum number of results.
            **kwargs: Backend options (must not change filter semantics).

        Returns:
            list[BaseModel]: Matching documents.

        Raises:
            QueryNotSupported: If the filter cannot be represented portably.
        """

    def find_one(self, where: dict, **kwargs) -> BaseModel | None:
        """Find first document matching *where*. Returns None when empty."""
        results = self.find(where=where, limit=1, **kwargs)
        return results[0] if results else None

    @abstractmethod
    def update_one(
        self,
        where: dict,
        set_fields: dict,
        upsert: bool = False,
        return_document: Literal["none", "before", "after"] = "none",
    ) -> Any:
        """Update exactly one matching document (partial field update).

        Args:
            where: Portable filter dict.
            set_fields: Fields to update (``$set`` semantics).
            upsert: Insert a new document when no match exists.
            return_document:
                ``"none"``   - return a backend update-result object.
                ``"before"`` - return document snapshot before update (or None).
                ``"after"``  - return document snapshot after update (or None).
        """

    @abstractmethod
    def delete_one(self, where: dict) -> int:
        """Delete exactly one matching document. Returns 0 or 1."""

    @abstractmethod
    def delete_many(self, where: dict) -> int:
        """Delete all matching documents. Returns deleted count."""

    @abstractmethod
    def distinct(self, field: str, where: dict | None = None) -> list[Any]:
        """Return distinct values for *field* among documents matching *where*."""

    # ── legacy compatibility API (id / full-document style) ─────────────
    # Prefer canonical query-style methods for new code:
    # insert_one / find / find_one / update_one / delete_one / delete_many / distinct

    @abstractmethod
    def insert(self, obj: BaseModel):
        """Legacy: insert a document by object. Prefer ``insert_one``."""

    @abstractmethod
    def get(self, id: str) -> BaseModel:
        """Legacy: retrieve a document by id. Prefer ``find_one``."""

    @abstractmethod
    def update(self, obj: BaseModel):
        """Legacy: full-document save by id/pk. Prefer ``update_one``."""

    @abstractmethod
    def delete(self, id: str):
        """Legacy: delete a document by id. Prefer ``delete_one``."""

    @abstractmethod
    def all(self) -> list[BaseModel]:
        """Legacy: retrieve all documents. Prefer ``find()``."""

    # ── introspection ───────────────────────────────────────────────────

    @abstractmethod
    def get_raw_model(self) -> Type[BaseModel]:
        """Get the raw document model class used by this backend."""
