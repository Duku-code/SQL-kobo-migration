import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


class SchemaManagerError(Exception):
    pass


SQL_TYPE_MAP = {
    "text": "NVARCHAR(MAX)",
    "integer": "INT",
    "decimal": "FLOAT",
    "select_one": "NVARCHAR(255)",
    "select_multiple": "NVARCHAR(MAX)",
    "date": "DATE",
    "datetime": "DATETIME2",
    "time": "TIME",
    "geopoint": "NVARCHAR(255)",
    "barcode": "NVARCHAR(255)",
    "photo": "NVARCHAR(MAX)",
    "audio": "NVARCHAR(MAX)",
    "video": "NVARCHAR(MAX)",
    "calculate": "NVARCHAR(MAX)",
    "note": "NVARCHAR(MAX)",
    "file": "NVARCHAR(MAX)",
}


def _normalize_sql_name(value: str) -> str:
    name = value.strip().lower()
    name = re.sub(r"[^a-z0-9_]+", "_", name)
    name = re.sub(r"__+", "_", name)
    name = name.strip("_")
    if not name:
        raise SchemaManagerError("Unable to generate a valid SQL name")
    if name[0].isdigit():
        name = f"col_{name}"
    return name


def _map_kobo_type(question: Dict[str, Any]) -> str:
    qtype = question.get("type", "text")
    if qtype.startswith("select one") or qtype == "select_one":
        return SQL_TYPE_MAP["select_one"]
    if qtype.startswith("select multiple") or qtype == "select_multiple":
        return SQL_TYPE_MAP["select_multiple"]

    if qtype in SQL_TYPE_MAP:
        return SQL_TYPE_MAP[qtype]

    logger.warning("Unknown Kobo question type '%s', defaulting to NVARCHAR(MAX)", qtype)
    return "NVARCHAR(MAX)"


class SchemaManager:
    def __init__(self, table_prefix: str = "kobo_"):
        self.table_prefix = table_prefix

    def form_to_table_name(self, form_name: str) -> str:
        normalized = _normalize_sql_name(form_name)
        return f"{self.table_prefix}{normalized}"

    def build_columns(self, survey_fields: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
        columns: List[Tuple[str, str]] = []
        for question in survey_fields:
            name = question.get("name")
            if not name:
                continue
            sql_name = _normalize_sql_name(name)
            sql_type = _map_kobo_type(question)
            columns.append((sql_name, sql_type))
        return columns

    def generate_create_table(self, form_definition: Dict[str, Any]) -> str:
        asset_name = form_definition.get("name") or form_definition.get("_id")
        if not asset_name:
            raise SchemaManagerError("Form definition must contain a name or _id")

        table_name = self.form_to_table_name(asset_name)
        survey = form_definition.get("survey")
        if not survey or not isinstance(survey, list):
            raise SchemaManagerError("Form definition does not contain valid survey fields")

        columns = self.build_columns(survey)
        if not columns:
            raise SchemaManagerError("No survey fields were found to create SQL columns")

        lines = [f"CREATE TABLE [{table_name}] (", "    [submission_id] NVARCHAR(255) PRIMARY KEY,"]
        for column_name, column_type in columns:
            lines.append(f"    [{column_name}] {column_type} NULL,")

        lines.append("    [received_at] DATETIME2 NULL")
        lines.append(")")

        return "\n".join(lines)

    def create_or_alter_table(self, form_definition: Dict[str, Any], existing_columns: List[str]) -> str:
        asset_name = form_definition.get("name") or form_definition.get("_id")
        table_name = self.form_to_table_name(asset_name)
        survey = form_definition.get("survey") or []
        columns = self.build_columns(survey)

        alter_statements: List[str] = []
        for column_name, column_type in columns:
            if column_name not in existing_columns:
                alter_statements.append(
                    f"ALTER TABLE [{table_name}] ADD [{column_name}] {column_type} NULL"
                )

        if alter_statements:
            return "\n".join(alter_statements)
        return "-- No schema changes detected"
