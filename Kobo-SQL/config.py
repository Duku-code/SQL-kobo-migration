from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from dotenv import load_dotenv
import os

# Load variables from .env in the project root, if present.
ENV_PATH = Path(__file__).resolve().parent / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)


@dataclass(frozen=True)
class Config:
    kobo_api_token: str
    kobo_base_url: str
    sql_server_host: str
    sql_server_database: str
    sql_server_user: str
    sql_server_password: str
    sql_server_driver: str
    sql_server_port: int
    streamlit_server_port: int

    @property
    def sqlalchemy_connection_string(self) -> str:
        driver = quote_plus(self.sql_server_driver)
        password = quote_plus(self.sql_server_password)
        return (
            f"mssql+pyodbc://{self.sql_server_user}:{password}@{self.sql_server_host},{self.sql_server_port}"
            f"/{self.sql_server_database}?driver={driver}&TrustServerCertificate=yes"
        )


def _streamlit_secrets() -> dict[str, Any]:
    try:
        import streamlit as st
        if st.secrets:
            return dict(st.secrets)
    except Exception:
        pass
    return {}


def _get_value(name: str, required: bool = True, default: str | None = None, source: dict[str, Any] | None = None) -> str:
    if source is not None:
        value = source.get(name, default)
    else:
        value = os.getenv(name, default)
    if required and not value:
        raise EnvironmentError(f"Missing required environment variable: {name}")
    return value


def get_config_defaults() -> dict[str, str]:
    defaults: dict[str, str] = {}
    source = _streamlit_secrets()
    for key in [
        "KOBO_API_TOKEN",
        "KOBO_BASE_URL",
        "SQL_SERVER_HOST",
        "SQL_SERVER_DATABASE",
        "SQL_SERVER_USER",
        "SQL_SERVER_PASSWORD",
        "SQL_SERVER_DRIVER",
        "SQL_SERVER_PORT",
        "STREAMLIT_SERVER_PORT",
    ]:
        value = source.get(key, os.getenv(key))
        if value is not None:
            defaults[key] = str(value)
    return defaults


def build_config(values: dict[str, Any] | None = None) -> Config:
    source = _streamlit_secrets()
    if values:
        source = {**source, **{k: v for k, v in values.items() if v is not None}}
    return Config(
        kobo_api_token=_get_value("KOBO_API_TOKEN", source=source),
        kobo_base_url=_get_value("KOBO_BASE_URL", source=source),
        sql_server_host=_get_value("SQL_SERVER_HOST", source=source),
        sql_server_database=_get_value("SQL_SERVER_DATABASE", source=source),
        sql_server_user=_get_value("SQL_SERVER_USER", source=source),
        sql_server_password=_get_value("SQL_SERVER_PASSWORD", source=source),
        sql_server_driver=_get_value(
            "SQL_SERVER_DRIVER", source=source, required=False, default="ODBC Driver 18 for SQL Server"
        ),
        sql_server_port=int(_get_value("SQL_SERVER_PORT", source=source, required=False, default="1433")),
        streamlit_server_port=int(_get_value("STREAMLIT_SERVER_PORT", source=source, required=False, default="8501")),
    )


def load_config() -> Config:
    return build_config()
