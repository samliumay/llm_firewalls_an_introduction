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
        project_root = Path(__file__).resolve().parents[1]
        database_env_file = (
            Path(env_file)
            if env_file
            else project_root / "configurations" / ".env"
        )
        load_dotenv(database_env_file)

        self._connection_settings = {
            "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "dbname": os.getenv("POSTGRES_DB", "firewall_bank"),
            "user": os.getenv("POSTGRES_USER", "firewall_user"),
            "password": os.getenv("POSTGRES_PASSWORD"),
        }
        self._firewall = BasicSQLFirewall()

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
        """
        if control_status:
            return self.safe_query(query, parameters)

        return self.direct_query(query, parameters)

    def direct_query(
        self,
        query: str,
        parameters: QueryParameters = None,
    ) -> QueryResult:
        """Execute SQL without firewall protection."""
        return self._run_query(query, parameters)

    def safe_query(
        self,
        query: str,
        parameters: QueryParameters = None,
    ) -> QueryResult:
        """Reject modifying SQL with the firewall, then execute the query."""
        self._firewall.validate_query(query)
        return self._run_query(query, parameters)

    def _run_query(
        self,
        query: str,
        parameters: QueryParameters,
    ) -> QueryResult:
        with psycopg.connect(
            **self._connection_settings,
            row_factory=dict_row,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, parameters)

                if cursor.description is not None:
                    return cursor.fetchall()

                return cursor.rowcount
