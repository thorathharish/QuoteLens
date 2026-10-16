"""Domain enumerations shared across modules and the API contract."""

from enum import StrEnum


class Provenance(StrEnum):
    """Where a displayed value comes from. Rendered as a badge on every value in the UI."""

    ACTUAL = "ACTUAL"
    CALCULATED = "CALCULATED"
    ASSUMED = "ASSUMED"
    UNAVAILABLE = "UNAVAILABLE"
    RECOMMENDED = "RECOMMENDED"


class EvidenceKind(StrEnum):
    DISTRIBUTOR_OFFER = "DISTRIBUTOR_OFFER"
    CATALOG_SNAPSHOT = "CATALOG_SNAPSHOT"
    BOM_CELL = "BOM_CELL"
    USER_OVERRIDE = "USER_OVERRIDE"
    RULE_EVAL = "RULE_EVAL"
    CALC_TRACE = "CALC_TRACE"


class SourceMode(StrEnum):
    LIVE = "LIVE"
    CACHE = "CACHE"
    DEMO_SNAPSHOT = "DEMO_SNAPSHOT"


class DataMode(StrEnum):
    """Order in which distributor data sources are consulted (ADR-0005)."""

    LIVE_FIRST = "live_first"
    CACHE_FIRST = "cache_first"
    DEMO_SNAPSHOT = "demo_snapshot"


class ProjectStatus(StrEnum):
    DRAFT = "DRAFT"
    MAPPING_REVIEW = "MAPPING_REVIEW"
    ANALYZING = "ANALYZING"
    IN_REVIEW = "IN_REVIEW"
    QUOTE_READY = "QUOTE_READY"
    FINALIZED = "FINALIZED"
    FAILED = "FAILED"


class IssueCode(StrEnum):
    MISSING_MPN = "MISSING_MPN"
    MISSING_MFR = "MISSING_MFR"
    QTY_INVALID = "QTY_INVALID"
    REFDES_QTY_MISMATCH = "REFDES_QTY_MISMATCH"
    DUPLICATE_MPN_CONFLICT = "DUPLICATE_MPN_CONFLICT"
    SUSPECT_MPN_FORMAT = "SUSPECT_MPN_FORMAT"
    UOM_CONFLICT = "UOM_CONFLICT"
    DNP = "DNP"


class MatchStatus(StrEnum):
    PENDING = "PENDING"
    MATCHED = "MATCHED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"


class Lifecycle(StrEnum):
    ACTIVE = "ACTIVE"
    NRND = "NRND"
    LAST_TIME_BUY = "LAST_TIME_BUY"
    EOL = "EOL"
    OBSOLETE = "OBSOLETE"
    UNKNOWN = "UNKNOWN"


class Severity(StrEnum):
    BLOCKER = "BLOCKER"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RiskCategory(StrEnum):
    DATA = "DATA"
    SUPPLY = "SUPPLY"
    PRICE = "PRICE"
    LIFECYCLE = "LIFECYCLE"
    QUANTITY = "QUANTITY"


class RiskStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    WAIVED = "WAIVED"


class NarrativeSource(StrEnum):
    TEMPLATE = "TEMPLATE"
    LLM = "LLM"


class ActionType(StrEnum):
    EDIT_LINE = "EDIT_LINE"
    SEARCH_ALTERNATIVES = "SEARCH_ALTERNATIVES"
    SELECT_OFFER = "SELECT_OFFER"
    CONFIRM_WITH_CUSTOMER = "CONFIRM_WITH_CUSTOMER"
    ACCEPT_RISK = "ACCEPT_RISK"


class FitClass(StrEnum):
    DROP_IN = "DROP_IN"
    FUNCTIONAL = "FUNCTIONAL"
    NOT_SUITABLE = "NOT_SUITABLE"


class CompareResult(StrEnum):
    MATCH = "MATCH"
    WITHIN_TOLERANCE = "WITHIN_TOLERANCE"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"


class AlternativeSource(StrEnum):
    NEXAR_SIMILAR = "NEXAR_SIMILAR"
    DIGIKEY_SUBSTITUTE = "DIGIKEY_SUBSTITUTE"
    CATALOG_CROSSREF = "CATALOG_CROSSREF"


class AlternativeStatus(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class JobType(StrEnum):
    ANALYSIS = "ANALYSIS"
    ALTERNATIVES = "ALTERNATIVES"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class QuoteStatus(StrEnum):
    DRAFT = "DRAFT"
    FINALIZED = "FINALIZED"


class DemoRole(StrEnum):
    """Role chosen in the UI role switcher. Used for audit attribution only (no auth)."""

    SOURCING = "SOURCING"
    QUOTE_ENGINEER = "QUOTE_ENGINEER"
    ENGINEERING = "ENGINEERING"
    MANAGER = "MANAGER"
    VIEWER = "VIEWER"


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
