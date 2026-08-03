"""Basic SQL firewall for the proof-of-concept application."""

import re


class QueryBlockedError(PermissionError):
    """Raised when the SQL firewall rejects a query."""


class BasicSQLFirewall:
    """Allow read queries and reject SQL keywords that can modify state."""

    _IGNORED_SQL = re.compile(
        r"--[^\r\n]*|/\*.*?\*/|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"",
        flags=re.DOTALL,
    )
    _BLOCKED_KEYWORDS = re.compile(
        r"\b("
        r"INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|"
        r"GRANT|REVOKE|COMMENT|COPY|CALL|DO|EXECUTE|PREPARE|"
        r"VACUUM|ANALYZE|CLUSTER|REINDEX|REFRESH|LOCK|SET|RESET|"
        r"DISCARD|INTO"
        r")\b",
        flags=re.IGNORECASE,
    )
    _ALLOWED_START = re.compile(
        r"^\s*(SELECT|WITH|SHOW|EXPLAIN)\b",
        flags=re.IGNORECASE,
    )

    def validate_query(self, query: str) -> None:
        """Raise QueryBlockedError unless the query appears read-only."""
        if not query or not query.strip():
            raise QueryBlockedError("The firewall blocked an empty query.")

        inspected_query = self._IGNORED_SQL.sub(" ", query)
        blocked_keyword = self._BLOCKED_KEYWORDS.search(inspected_query)

        if blocked_keyword:
            raise QueryBlockedError(
                "The firewall blocked the SQL keyword "
                f"{blocked_keyword.group(1).upper()}."
            )

        if not self._ALLOWED_START.match(inspected_query):
            raise QueryBlockedError(
                "The firewall only allows SELECT, WITH, SHOW, or EXPLAIN queries."
            )
