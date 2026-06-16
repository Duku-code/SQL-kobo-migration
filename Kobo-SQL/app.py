import logging
import os
from typing import Optional

import streamlit as st
import config

build_config = getattr(config, "build_config", None)
get_config_defaults = getattr(config, "get_config_defaults", lambda: {})
if build_config is None:
    def build_config(values=None):
        if values:
            for key, value in values.items():
                if value is not None:
                    os.environ[key] = str(value)
        return config.load_config()

from db_manager import DBManager
from kobo_client import KoboClient, KoboClientError
from schema_manager import SchemaManager, SchemaManagerError
from sync_engine import SyncEngine, SyncEngineError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def generate_create_table_sql(config_values: dict[str, str], form_id: str) -> str:
    if not form_id:
        raise ValueError("Form ID is required to generate SQL.")

    token = config_values.get("KOBO_API_TOKEN")
    base_url = config_values.get("KOBO_BASE_URL")
    if not token:
        raise ValueError("Kobo API token is required to generate SQL.")
    if not base_url:
        raise ValueError("Kobo Base URL is required to generate SQL.")

    class KoboConfig:
        pass

    kobo_config = KoboConfig()
    kobo_config.kobo_api_token = token
    kobo_config.kobo_base_url = base_url

    client = KoboClient(kobo_config)
    schema_manager = SchemaManager()
    form_definition = client.fetch_form_definition(form_id)
    return schema_manager.generate_create_table(form_definition)


def fetch_database_list(config_values: dict[str, str]) -> list[str]:
    list_values = {**config_values}
    list_values["SQL_SERVER_DATABASE"] = "master"
    temp_config = build_config(list_values)
    db_manager = DBManager(temp_config)
    return db_manager.list_databases()


def main():
    st.set_page_config(page_title="Kobo to SQL Sync", layout="wide")

    st.title("Kobo to SQL Server Sync")
    st.markdown(
        "This app syncs KoboToolbox data into SQL Server. Enter credentials here or use `.env` / Streamlit Secrets."
    )

    defaults = get_config_defaults()
    with st.sidebar:
        st.header("Credentials & settings")
        st.markdown(
            "Enter your Kobo API token and SQL Server settings here to run the sync. "
            "Values are also loaded from `.env` locally or from Streamlit Secrets in deployment."
        )

        kobo_api_token = st.text_input(
            "Kobo API Token",
            value=defaults.get("KOBO_API_TOKEN", ""),
            type="password",
            help="Your KoboToolbox API token",
        )
        kobo_base_url = st.text_input(
            "Kobo Base URL",
            value=defaults.get("KOBO_BASE_URL", "https://kf.kobotoolbox.org"),
        )
        sql_server_host = st.text_input(
            "SQL Server Host",
            value=defaults.get("SQL_SERVER_HOST", ""),
        )
        sql_server_auth_method = st.selectbox(
            "SQL Server Authentication",
            options=["SQL Server Authentication", "Windows Authentication"],
            index=0 if defaults.get("SQL_SERVER_AUTH_METHOD", "sql") == "sql" else 1,
        )
        sql_server_user = ""
        sql_server_password = ""
        if sql_server_auth_method == "SQL Server Authentication":
            sql_server_user = st.text_input(
                "SQL Server User",
                value=defaults.get("SQL_SERVER_USER", ""),
            )
            sql_server_password = st.text_input(
                "SQL Server Password",
                value=defaults.get("SQL_SERVER_PASSWORD", ""),
                type="password",
            )
        sql_server_driver = st.text_input(
            "SQL Server Driver",
            value=defaults.get("SQL_SERVER_DRIVER", "ODBC Driver 18 for SQL Server"),
        )
        sql_server_port = st.text_input(
            "SQL Server Port",
            value=defaults.get("SQL_SERVER_PORT", "1433"),
        )

        database_options = []
        if sql_server_host and (sql_server_auth_method == "Windows Authentication" or (sql_server_user and sql_server_password)):
            try:
                list_values = {
                    "KOBO_API_TOKEN": kobo_api_token.strip() or defaults.get("KOBO_API_TOKEN"),
                    "KOBO_BASE_URL": kobo_base_url.strip() or defaults.get("KOBO_BASE_URL"),
                    "SQL_SERVER_HOST": sql_server_host.strip(),
                    "SQL_SERVER_AUTH_METHOD": "windows" if sql_server_auth_method == "Windows Authentication" else "sql",
                    "SQL_SERVER_USER": sql_server_user.strip() or None,
                    "SQL_SERVER_PASSWORD": sql_server_password.strip() or None,
                    "SQL_SERVER_DRIVER": sql_server_driver.strip(),
                    "SQL_SERVER_PORT": sql_server_port.strip(),
                    "SQL_SERVER_DATABASE": "master",
                }
                database_options = fetch_database_list(list_values)
            except Exception:
                database_options = []

        if database_options:
            sql_server_database = st.selectbox(
                "Select SQL Server Database",
                options=database_options,
                index=database_options.index(defaults.get("SQL_SERVER_DATABASE")) if defaults.get("SQL_SERVER_DATABASE") in database_options else 0,
            )
        else:
            sql_server_database = st.text_input(
                "SQL Server Database",
                value=defaults.get("SQL_SERVER_DATABASE", ""),
            )
        streamlit_server_port = st.text_input(
            "Streamlit Port",
            value=defaults.get("STREAMLIT_SERVER_PORT", "8501"),
        )

        st.markdown("---")
        st.code(
            """
KOBO_API_TOKEN=your_token_here
KOBO_BASE_URL=https://kf.kobotoolbox.org
SQL_SERVER_HOST=your_sql_server_host
SQL_SERVER_DATABASE=your_database
SQL_SERVER_USER=your_user
SQL_SERVER_PASSWORD=your_password
SQL_SERVER_DRIVER=ODBC Driver 18 for SQL Server
SQL_SERVER_PORT=1433
STREAMLIT_SERVER_PORT=8501
""",
            language="ini",
        )

    config_values = {
        "KOBO_API_TOKEN": kobo_api_token.strip() or None,
        "KOBO_BASE_URL": kobo_base_url.strip() or None,
        "SQL_SERVER_HOST": sql_server_host.strip() or None,
        "SQL_SERVER_DATABASE": sql_server_database.strip() or None,
        "SQL_SERVER_USER": sql_server_user.strip() or None,
        "SQL_SERVER_PASSWORD": sql_server_password.strip() or None,
        "SQL_SERVER_AUTH_METHOD": "windows" if sql_server_auth_method == "Windows Authentication" else "sql",
        "SQL_SERVER_DRIVER": sql_server_driver.strip() or None,
        "SQL_SERVER_PORT": sql_server_port.strip() or None,
        "STREAMLIT_SERVER_PORT": streamlit_server_port.strip() or None,
    }

    config = None
    required = {
        "KOBO_API_TOKEN": bool(config_values["KOBO_API_TOKEN"] or defaults.get("KOBO_API_TOKEN")),
        "KOBO_BASE_URL": bool(config_values["KOBO_BASE_URL"] or defaults.get("KOBO_BASE_URL")),
        "SQL_SERVER_HOST": bool(config_values["SQL_SERVER_HOST"] or defaults.get("SQL_SERVER_HOST")),
        "SQL_SERVER_DATABASE": bool(config_values["SQL_SERVER_DATABASE"] or defaults.get("SQL_SERVER_DATABASE")),
    }
    if config_values["SQL_SERVER_AUTH_METHOD"] == "sql":
        required["SQL_SERVER_USER"] = bool(config_values["SQL_SERVER_USER"] or defaults.get("SQL_SERVER_USER"))
        required["SQL_SERVER_PASSWORD"] = bool(config_values["SQL_SERVER_PASSWORD"] or defaults.get("SQL_SERVER_PASSWORD"))
    else:
        required["SQL_SERVER_USER"] = True
        required["SQL_SERVER_PASSWORD"] = True

    with st.expander("Configuration status (no secrets shown)"):
        for k, v in required.items():
            st.write(f"{k}: {'✅ set' if v else '❌ missing'}")

    st.sidebar.markdown("---")
    st.sidebar.write("Kobo Base URL:")
    st.sidebar.write(config_values["KOBO_BASE_URL"] or defaults.get("KOBO_BASE_URL", "Not set"))
    st.sidebar.write("SQL Server Host:")
    st.sidebar.write(config_values["SQL_SERVER_HOST"] or defaults.get("SQL_SERVER_HOST", "Not set"))
    st.sidebar.write("Database:")
    st.sidebar.write(config_values["SQL_SERVER_DATABASE"] or defaults.get("SQL_SERVER_DATABASE", "Not set"))

    with st.form(key="generate_sql_form"):
        generate_form_id = st.text_input(
            "Kobo Form ID for SQL DDL",
            help="Enter the Kobo form asset ID to generate table creation SQL.",
        )
        generate_sql = st.form_submit_button("Generate SQL DDL")

    if generate_sql:
        if not generate_form_id:
            st.warning("Please provide a Kobo Form ID to generate SQL.")
        else:
            try:
                create_sql = generate_create_table_sql(config_values, generate_form_id)
                st.success("SQL DDL generated. Copy it into SQL Server and run it.")
                st.code(create_sql, language="sql")
            except (ValueError, KoboClientError, SchemaManagerError) as exc:
                st.error(f"SQL generation failed: {exc}")
            except Exception as exc:
                st.error(f"Unexpected SQL generation error: {exc}")

    st.markdown("---")
    with st.form(key="sync_form"):
        form_id = st.text_input("Kobo Form ID for Sync", help="Enter the Kobo form asset ID to sync.")
        run_sync = st.form_submit_button("Run Sync")

    if run_sync:
        if not form_id:
            st.warning("Please provide a Kobo Form ID to sync.")
        else:
            try:
                config = build_config(config_values)
            except Exception as exc:
                st.error(f"Configuration error: {exc}")
                return

            sync_status = st.empty()
            sync_details = st.empty()
            try:
                sync_engine = SyncEngine(config=config)
                sync_status.info("Starting sync...")
                result = sync_engine.sync_form(form_id)
                sync_status.success("Sync completed successfully.")
                sync_details.json(result)
            except SyncEngineError as exc:
                sync_status.error(f"Sync failed: {exc}")
            except Exception as exc:
                sync_status.error(f"Unexpected error: {exc}")

    st.markdown("---")
    st.subheader("Manual sync instructions")
    st.write(
        "Use the sidebar to verify your `.env` values, then enter a Kobo form ID and click `Run Sync`."
    )
    st.write(
        "The app currently supports batch sync via Kobo API. Webhook handling can be added as a separate endpoint or function later."
    )


if __name__ == "__main__":
    main()
