import logging
from dataclasses import replace
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from config import load_config

logger = logging.getLogger(__name__)


class DBManagerError(Exception):
    pass


class DBManager:
    def __init__(self, config=None, override_database: str | None = None):
        self.config = config or load_config()
        if override_database:
            self.config = replace(self.config, sql_server_database=override_database)
        self.engine = self._create_engine()

    def _create_engine(self) -> Engine:
        connection_string = self.config.sqlalchemy_connection_string
        logger.debug("Creating SQLAlchemy engine with %s", connection_string)
        try:
            engine = create_engine(connection_string, fast_executemany=True)
            return engine
        except SQLAlchemyError as exc:
            logger.exception("Failed to create database engine")
            raise DBManagerError("Failed to create database engine") from exc

    def get_table_columns(self, table_name: str) -> List[str]:
        inspector = inspect(self.engine)
        try:
            columns = inspector.get_columns(table_name)
            return [col["name"] for col in columns]
        except SQLAlchemyError as exc:
            logger.exception("Failed to inspect table columns for %s", table_name)
            raise DBManagerError(f"Failed to inspect table columns for {table_name}") from exc

    def execute_ddl(self, ddl_sql: str) -> None:
        logger.info("Executing DDL:\n%s", ddl_sql)
        try:
            with self.engine.begin() as conn:
                conn.execute(text(ddl_sql))
        except SQLAlchemyError as exc:
            logger.exception("DDL execution failed")
            raise DBManagerError("DDL execution failed") from exc

    def ensure_table(self, create_table_sql: str) -> None:
        self.execute_ddl(create_table_sql)

    def upsert_submission(self, table_name: str, submission: Dict[str, Any]) -> None:
        if "submission_id" not in submission:
            raise DBManagerError("submission record must include submission_id")

        columns = list(submission.keys())
        params = {col: submission[col] for col in columns}
        column_list = ", ".join(f"[{col}]" for col in columns)
        select_list = ", ".join(f":{col} AS [{col}]" for col in columns)
        update_list = ", ".join(f"target.[{col}] = source.[{col}]" for col in columns if col != "submission_id")

        merge_sql = f"""
MERGE INTO [{table_name}] AS target
USING (SELECT {select_list}) AS source
ON target.[submission_id] = source.[submission_id]
WHEN MATCHED THEN
    UPDATE SET {update_list}
WHEN NOT MATCHED THEN
    INSERT ({column_list})
    VALUES ({', '.join(f'source.[{col}]' for col in columns)});
"""
        try:
            with self.engine.begin() as conn:
                conn.execute(text(merge_sql), params)
        except SQLAlchemyError as exc:
            logger.exception("Upsert failed for submission_id=%s", submission.get("submission_id"))
            raise DBManagerError("Upsert failed") from exc

    def bulk_upsert_submissions(self, table_name: str, submissions: Iterable[Dict[str, Any]]) -> int:
        submissions = list(submissions)
        if not submissions:
            return 0

        inserted = 0
        for submission in submissions:
            self.upsert_submission(table_name, submission)
            inserted += 1
        return inserted

    def get_connection(self):
        return self.engine.connect()

    def list_databases(self) -> List[str]:
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("SELECT name FROM sys.databases ORDER BY name"))
                return [row[0] for row in result]
        except SQLAlchemyError as exc:
            logger.exception("Failed to list databases")
            raise DBManagerError("Failed to list databases") from exc
