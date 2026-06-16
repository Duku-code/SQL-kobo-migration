# Kobo-to-SQL Humanitarian Data Pipeline

A Python-based Streamlit application to sync KoboToolbox submissions into Microsoft SQL Server.

## Features
- Automatically generate SQL Server table schema from Kobo form definitions
- Fetch Kobo submissions via Kobo API v2
- Insert/update rows in SQL Server using an upsert workflow
- Simple Streamlit dashboard for manual sync control
- Secure configuration via `.env`

## Project Structure
- `app.py`: Streamlit UI entrypoint
- `config.py`: Loads secure settings from `.env`
- `kobo_client.py`: KoboToolbox API integration
- `schema_manager.py`: Kobo schema to SQL DDL mapping
- `db_manager.py`: SQL Server connection, schema execution, and upsert operations
- `sync_engine.py`: Orchestrates the end-to-end sync process
- `requirements.txt`: Python dependencies
- `.env.example`: Template for environment variables

## Setup
1. Copy `.env.example` to `.env`
2. Fill in your Kobo and SQL Server credentials
3. Install dependencies:
   ```powershell
   py -3 -m pip install -r requirements.txt
   ```
4. Run the app:
   ```powershell
   py -3 app.py
   ```

## Notes
- Do not commit `.env` to source control.
- If network access to PyPI is restricted, configure a proxy or use an offline package cache.
- Ensure the `mssql` or `ODBC Driver 18 for SQL Server` driver is installed on Windows.

## Example `.env`
```ini
KOBO_API_TOKEN=your_token_here
KOBO_BASE_URL=https://kf.kobotoolbox.org
SQL_SERVER_HOST=your_sql_server_host
SQL_SERVER_PORT=1433
SQL_SERVER_DATABASE=your_database
SQL_SERVER_USER=your_user
SQL_SERVER_PASSWORD=your_password
SQL_SERVER_DRIVER=ODBC Driver 18 for SQL Server
STREAMLIT_SERVER_PORT=8501
```
