"""Typed repositories over the document store (Firestore layout: LLD §3.3)."""

from app.domain.facts import Evidence
from app.domain.models import (
    Alternative,
    AuditEvent,
    BomLine,
    ChatMessage,
    Job,
    Offer,
    Project,
    QuoteVersion,
    Risk,
)
from app.infra.repositories.base import (
    DocumentStore,
    Filter,
    OrderBy,
    Page,
    TypedCollection,
)

__all__ = ["DocumentStore", "Filter", "OrderBy", "Page", "Repositories", "TypedCollection"]


class Repositories:
    """Entry point for persistence. One instance per process, built in the app container."""

    def __init__(self, store: DocumentStore) -> None:
        self.store = store
        self.projects = TypedCollection(store, ("projects",), Project)
        self.jobs = TypedCollection(store, ("jobs",), Job)

    def lines(self, project_id: str) -> TypedCollection[BomLine]:
        return TypedCollection(self.store, ("projects", project_id, "lines"), BomLine)

    def offers(self, project_id: str) -> TypedCollection[Offer]:
        return TypedCollection(self.store, ("projects", project_id, "offers"), Offer)

    def risks(self, project_id: str) -> TypedCollection[Risk]:
        return TypedCollection(self.store, ("projects", project_id, "risks"), Risk)

    def alternatives(self, project_id: str) -> TypedCollection[Alternative]:
        return TypedCollection(self.store, ("projects", project_id, "alternatives"), Alternative)

    def evidence(self, project_id: str) -> TypedCollection[Evidence]:
        return TypedCollection(self.store, ("projects", project_id, "evidence"), Evidence)

    def audit(self, project_id: str) -> TypedCollection[AuditEvent]:
        return TypedCollection(self.store, ("projects", project_id, "audit"), AuditEvent)

    def quotes(self, project_id: str) -> TypedCollection[QuoteVersion]:
        return TypedCollection(self.store, ("projects", project_id, "quotes"), QuoteVersion)

    def chat_messages(self, project_id: str, session_id: str) -> TypedCollection[ChatMessage]:
        return TypedCollection(
            self.store, ("projects", project_id, "chat", session_id, "messages"), ChatMessage
        )
