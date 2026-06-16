import logging
from typing import Any, Dict, Iterable, List, Optional

from db_manager import DBManager, DBManagerError
from kobo_client import KoboClient, KoboClientError
from schema_manager import SchemaManager, SchemaManagerError

logger = logging.getLogger(__name__)


class SyncEngineError(Exception):
    pass


class SyncEngine:
    def __init__(
        self,
        config: Any = None,
        kobo_client: Optional[KoboClient] = None,
        db_manager: Optional[DBManager] = None,
    ):
        self.config = config
        self.kobo_client = kobo_client or (KoboClient(config) if config is not None else KoboClient())
        self.db_manager = db_manager or (DBManager(config) if config is not None else DBManager())
        self.schema_manager = SchemaManager()

    def _normalize_submission(self, submission: Dict[str, Any]) -> Dict[str, Any]:
        normalized = {}
        submission_id = submission.get("_id") or submission.get("id") or submission.get("submission_id")
        if not submission_id:
            raise SyncEngineError("Submission is missing an identifier (_id or id)")

        normalized["submission_id"] = str(submission_id)

        received_at = (
            submission.get("_submission_time")
            or submission.get("submission_time")
            or submission.get("created_at")
            or submission.get("created_on")
        )
        normalized["received_at"] = received_at

        for key, value in submission.items():
            if key in {"_id", "id", "submission_id", "_submission_time", "submission_time", "created_at", "created_on"}:
                continue
            if isinstance(value, (dict, list)):
                normalized[key] = str(value)
            else:
                normalized[key] = value

        return normalized

    def _flatten_submissions(self, submissions: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized_rows: List[Dict[str, Any]] = []
        for submission in submissions:
            normalized_rows.append(self._normalize_submission(submission))
        return normalized_rows

    def _fetch_all_submissions(self, form_id: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        page_params = dict(params or {})
        page_params.setdefault("format", "json")
        page_params.setdefault("limit", 1000)

        while True:
            response = self.kobo_client.fetch_submissions(form_id, params=page_params)
            if not isinstance(response, dict):
                raise SyncEngineError("Unexpected Kobo submissions response format")

            batch = response.get("results") or response.get("data") or response
            if isinstance(batch, dict) and "results" in batch:
                batch = batch["results"]

            if not isinstance(batch, list):
                raise SyncEngineError("Unable to parse Kobo submissions response")

            results.extend(batch)

            next_url = response.get("next")
            if not next_url:
                break

            # API may include a next URL, but we keep using page_params if absent.
            page_params["offset"] = len(results)

        return results

    def sync_form(self, form_id: str) -> Dict[str, Any]:
        logger.info("Starting Kobo sync for form_id=%s", form_id)
        try:
            form_definition = self.kobo_client.fetch_form_definition(form_id)
        except KoboClientError as exc:
            raise SyncEngineError("Failed to fetch Kobo form definition") from exc

        try:
            create_table_sql = self.schema_manager.generate_create_table(form_definition)
        except SchemaManagerError as exc:
            raise SyncEngineError("Failed to generate create table DDL") from exc

        table_name = self.schema_manager.form_to_table_name(form_definition.get("name") or form_definition.get("_id"))

        existing_columns: List[str] = []
        try:
            existing_columns = self.db_manager.get_table_columns(table_name)
        except DBManagerError:
            logger.info("Table %s does not exist or cannot be inspected yet; creating it", table_name)
            self.db_manager.execute_ddl(create_table_sql)
            existing_columns = self.db_manager.get_table_columns(table_name)

        alter_sql = self.schema_manager.create_or_alter_table(form_definition, existing_columns)
        if alter_sql and not alter_sql.strip().startswith("--"):
            self.db_manager.execute_ddl(alter_sql)

        try:
            submissions = self._fetch_all_submissions(form_id)
        except KoboClientError as exc:
            raise SyncEngineError("Failed to fetch Kobo submissions") from exc

        rows = self._flatten_submissions(submissions)
        inserted = self.db_manager.bulk_upsert_submissions(table_name, rows)

        logger.info("Sync complete for form_id=%s. Loaded %s submissions.", form_id, inserted)
        return {
            "form_id": form_id,
            "table_name": table_name,
            "submissions_fetched": len(submissions),
            "rows_upserted": inserted,
        }

    def process_webhook(self, payload: Dict[str, Any], form_id: Optional[str] = None) -> Dict[str, Any]:
        logger.info("Processing webhook payload for form_id=%s", form_id)
        submission = self.kobo_client.parse_webhook_payload(payload)
        row = self._normalize_submission(submission)

        if form_id:
            form_definition = self.kobo_client.fetch_form_definition(form_id)
            table_name = self.schema_manager.form_to_table_name(form_definition.get("name") or form_definition.get("_id"))
        else:
            raise SyncEngineError("Form ID is required for webhook processing")

        try:
            existing_columns = self.db_manager.get_table_columns(table_name)
        except DBManagerError:
            raise SyncEngineError(f"Target table {table_name} does not exist") from None

        missing_columns = [col for col in row.keys() if col not in existing_columns]
        if missing_columns:
            raise SyncEngineError(f"Webhook payload contains unknown columns: {missing_columns}")

        self.db_manager.upsert_submission(table_name, row)
        return {"table_name": table_name, "submission_id": row["submission_id"]}
