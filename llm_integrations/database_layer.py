"""PostgreSQL access layer used by the LLM firewall proof of concept."""

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from firewall.firewall_class import BasicSQLFirewall


QueryParameters = Sequence[Any] | Mapping[str, Any] | None
QueryResult = list[dict[str, Any]] | int


class DatabaseManagement:
    """Route model-generated SQL through direct or controlled execution."""

    def __init__(self, env_file: str | Path | None = None) -> None:
        """Load database settings and prepare the SQL firewall.

        Args:
            env_file: Optional path to a database environment file. When it is
                omitted, configurations/.env is used.
        """
        # Find configurations/.env relative to the project, regardless of the
        # directory from which the Python program was started.
        project_root = Path(__file__).resolve().parents[1]
        database_env_file = (
            Path(env_file)
            if env_file
            else project_root / "configurations" / ".env"
        )
        load_dotenv(database_env_file)

        # These defaults match the local PostgreSQL Docker Compose service.
        self._connection_settings = {
            "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "dbname": os.getenv("POSTGRES_DB", "firewall_bank"),
            "user": os.getenv("POSTGRES_USER", "firewall_user"),
            "password": os.getenv("POSTGRES_PASSWORD"),
        }
        self._firewall = BasicSQLFirewall()

        # PostgreSQL requires the real local password from configurations/.env.
        if not self._connection_settings["password"]:
            raise ValueError(
                "POSTGRES_PASSWORD is missing. Set it in configurations/.env."
            )

    def execute_query(
        self,
        query: str,
        parameters: QueryParameters = None,
        control_status: bool = False,
    ) -> QueryResult:
        """Route a query to safe or direct execution.

        A false control status executes without firewall inspection. A true
        control status checks the query with the firewall before execution.

        Returns:
            Database rows for a query that produces rows, otherwise the number
            of rows affected by the statement.
        """
        # Security mode is chosen by the application, not by the LLM tool call.
        if control_status:
            return self.safe_query(query, parameters)

        return self.direct_query(query, parameters)

    def direct_query(
        self,
        query: str,
        parameters: QueryParameters = None,
    ) -> QueryResult:
        """Execute SQL without inspecting it with the firewall.

        This deliberately unsafe path exists to demonstrate the behavior of an
        application that trusts model-generated SQL.
        """
        return self._run_query(query, parameters)

    def safe_query(
        self,
        query: str,
        parameters: QueryParameters = None,
    ) -> QueryResult:
        """Validate SQL with the firewall before executing it.

        QueryBlockedError is raised by the firewall when the SQL is considered
        unsafe. Only validated SQL reaches the common database executor.
        """
        self._firewall.validate_query(query)
        return self._run_query(query, parameters)

    def _run_query(
        self,
        query: str,
        parameters: QueryParameters,
    ) -> QueryResult:
        """Open a connection, execute one SQL statement, and format its result."""
        # The connection context commits successful modifications, rolls back
        # failures, and closes the connection when execution finishes.
        with psycopg.connect(
            **self._connection_settings,
            row_factory=dict_row,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, parameters)

                # SELECT-like statements provide column information and rows.
                if cursor.description is not None:
                    return cursor.fetchall()

                # INSERT, UPDATE, and DELETE return their affected-row count.
                return cursor.rowcount
