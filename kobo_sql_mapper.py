import sys
import json
import os
import pandas as pd
import pyodbc
import requests
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QLineEdit,
    QFileDialog, QVBoxLayout, QComboBox, QMessageBox, QTextEdit, QHBoxLayout, QCheckBox
)
from PyQt5.QtCore import QTimer

class KoboSqlMapper(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Kobo to SQL Mapper with Full Login & Auto-Sync')
        self.db_list = []
        self.db_conn = None
        self.chosen_db = ''
        self.form_columns = []  # List of (name, type)
        self.table_name = 'kobo_survey'
        self.survey_form_path = ''
        self.survey_form_type = 'json'  # or 'xlsx'
        self.kobo_token = ''
        self.kobo_username = ''
        self.kobo_password = ''
        self.kobo_form_id = ''
        self.last_id = 0  # for incremental sync
        self.sync_timer = QTimer()
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # ------------ SQL CONNECTION ---------------
        layout.addWidget(QLabel('SQL Server Address:'))
        self.server_input = QLineEdit()
        self.server_input.setPlaceholderText('server_name or server_addr\\instance')
        layout.addWidget(self.server_input)

        self.win_auth_checkbox = QCheckBox("Use Windows Authentication")
        self.win_auth_checkbox.stateChanged.connect(self.toggle_auth_fields)
        layout.addWidget(self.win_auth_checkbox)

        cred_layout = QHBoxLayout()
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("Username")
        cred_layout.addWidget(self.user_input)
        self.pw_input = QLineEdit()
        self.pw_input.setEchoMode(QLineEdit.Password)
        self.pw_input.setPlaceholderText("Password")
        cred_layout.addWidget(self.pw_input)
        layout.addLayout(cred_layout)

        self.connect_btn = QPushButton("Connect to SQL Server")
        self.connect_btn.clicked.connect(self.get_databases)
        layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("Disconnect Database")
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.clicked.connect(self.disconnect_db)
        layout.addWidget(self.disconnect_btn)

        # ------------ KOBO LOGIN -----------------
        layout.addWidget(QLabel("Kobo Username:"))
        self.kobo_username_input = QLineEdit()
        self.kobo_username_input.setPlaceholderText("me@example.com")
        layout.addWidget(self.kobo_username_input)
        layout.addWidget(QLabel("Kobo Password:"))
        self.kobo_password_input = QLineEdit()
        self.kobo_password_input.setPlaceholderText("Kobo password")
        self.kobo_password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.kobo_password_input)
        self.login_kobo_btn = QPushButton("Login to Kobo")
        self.login_kobo_btn.clicked.connect(self.kobo_login)
        layout.addWidget(self.login_kobo_btn)

        self.kobo_login_status = QLabel("")
        layout.addWidget(self.kobo_login_status)

        # ------------ KOBO FORM INFO --------------
        layout.addWidget(QLabel('Select Database:'))
        self.db_combo = QComboBox()
        self.db_combo.setEnabled(False)
        layout.addWidget(self.db_combo)

        layout.addWidget(QLabel("Kobo Form ID (asset uid):"))
        self.kobo_form_id_input = QLineEdit()
        self.kobo_form_id_input.setPlaceholderText("e.g. aBcDExYz123WVWv")
        layout.addWidget(self.kobo_form_id_input)

        # Survey form structure
        self.survey_label = QLabel('Upload Survey Form Structure (.xlsx or .json)')
        layout.addWidget(self.survey_label)
        self.upload_survey_btn = QPushButton('Upload Survey Form')
        self.upload_survey_btn.clicked.connect(self.upload_survey_form)
        layout.addWidget(self.upload_survey_btn)

        layout.addWidget(QLabel('Choose Table Name:'))
        self.table_input = QLineEdit()
        self.table_input.setText("kobo_survey")
        layout.addWidget(self.table_input)

        self.create_btn = QPushButton('Generate CREATE TABLE SQL')
        self.create_btn.clicked.connect(self.show_create_sql)
        layout.addWidget(self.create_btn)

        self.sql_text = QTextEdit()
        self.sql_text.setPlaceholderText('Your CREATE TABLE statement will appear here.')
        layout.addWidget(self.sql_text)

        self.check_table_btn = QPushButton('Check Table Exists (after you create it)')
        self.check_table_btn.clicked.connect(self.check_table)
        layout.addWidget(self.check_table_btn)

        # Only one button for data sync
        self.map_btn = QPushButton('Map Kobo Data to SQL (and Enable Auto-Sync)')
        self.map_btn.clicked.connect(self.map_and_start_sync)
        self.map_btn.setEnabled(False)
        layout.addWidget(self.map_btn)

        self.stop_sync_btn = QPushButton('Stop Auto-Sync')
        self.stop_sync_btn.clicked.connect(self.stop_sync)
        self.stop_sync_btn.setEnabled(False)
        layout.addWidget(self.stop_sync_btn)

        self.setLayout(layout)
        self.toggle_auth_fields(self.win_auth_checkbox.checkState())

        self.sync_timer.setInterval(5 * 60 * 1000)  # 5 minutes
        self.sync_timer.timeout.connect(self.run_sync_once)

    def toggle_auth_fields(self, state):
        if self.win_auth_checkbox.isChecked():
            self.user_input.setDisabled(True)
            self.pw_input.setDisabled(True)
        else:
            self.user_input.setDisabled(False)
            self.pw_input.setDisabled(False)

    def get_connection_string(self, database=None):
        server = self.server_input.text().strip()
        if self.win_auth_checkbox.isChecked():
            conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};"
            if database:
                conn_str += f"DATABASE={database};"
            conn_str += "Trusted_Connection=yes;"
        else:
            user = self.user_input.text().strip()
            pw = self.pw_input.text().strip()
            conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};UID={user};PWD={pw};"
            if database:
                conn_str += f"DATABASE={database};"
        return conn_str

    def get_databases(self):
        try:
            conn = pyodbc.connect(self.get_connection_string(), timeout=5)
            cursor = conn.cursor()
            system_dbs = {'master', 'model', 'msdb', 'tempdb', 'SSISDB'}
            cursor.execute("SELECT name FROM sys.databases")
            self.db_list = [row[0] for row in cursor.fetchall() if row[0] not in system_dbs]
            self.db_combo.clear()
            self.db_combo.addItems(self.db_list)
            self.db_combo.setEnabled(True)
            self.db_combo.currentIndexChanged.connect(self.db_selected)
            self.db_selected()
            self.disconnect_btn.setEnabled(True)
            QMessageBox.information(self, "Connected", "SQL Server connected!")
        except Exception as e:
            QMessageBox.critical(self, "Connect failed", str(e))

    def disconnect_db(self):
        try:
            if self.db_conn is not None:
                self.db_conn.close()
                self.db_conn = None
            self.db_combo.clear()
            self.db_combo.setEnabled(False)
            self.disconnect_btn.setEnabled(False)
            self.map_btn.setEnabled(False)
            self.stop_sync_btn.setEnabled(False)
            QMessageBox.information(self, "Disconnected", "Database connection has been closed.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error disconnecting: {e}")

    def db_selected(self):
        self.chosen_db = self.db_combo.currentText()
        try:
            self.db_conn = pyodbc.connect(self.get_connection_string(database=self.chosen_db), timeout=5)
        except Exception as e:
            self.db_conn = None
            QMessageBox.warning(self, "Permission Error",
                                f"Cannot access database '{self.chosen_db}'. Please pick a different database.\n\n{e}")
            self.map_btn.setEnabled(False)
            self.stop_sync_btn.setEnabled(False)

    def upload_survey_form(self):
        fileName, _ = QFileDialog.getOpenFileName(self, "Select Kobo Survey Form", "", "Excel Files (*.xlsx);;JSON Files (*.json)")
        if fileName:
            ext = os.path.splitext(fileName)[1].lower()
            self.survey_form_path = fileName
            if ext == ".xlsx":
                self.survey_form_type = "xlsx"
                self.survey_label.setText(f"Survey XLSX: {os.path.basename(fileName)}")
                self.form_columns = self.extract_columns_from_xlsx(fileName)
            elif ext == ".json":
                self.survey_form_type = "json"
                self.survey_label.setText(f"Survey JSON: {os.path.basename(fileName)}")
                self.form_columns = self.extract_columns_from_json(fileName)
            else:
                QMessageBox.warning(self, "Invalid File", "File must be XLSX or JSON!")
                self.survey_form_path = ""
                self.form_columns = []

    def extract_columns_from_xlsx(self, path):
        try:
            df = pd.read_excel(path, sheet_name="survey")
        except Exception as e:
            QMessageBox.critical(self, "XLSX Error", f"Cannot read sheet 'survey': {e}")
            return []
        columns = []
        for _, row in df.iterrows():
            qname, qtype = str(row.get('name', '')).strip(), str(row.get('type', '')).strip().lower()
            if not qname or any(x in qtype for x in ['begin group', 'end group', 'note']):
                continue
            if qtype.startswith('int') or qtype == 'calculate':
                coltype = 'INT'
            elif qtype.startswith('decimal'):
                coltype = 'FLOAT'
            elif qtype in ['date']:
                coltype = 'DATE'
            elif 'time' in qtype or qtype == 'start' or qtype == 'end':
                coltype = 'DATETIME'
            else:
                coltype = 'NVARCHAR(MAX)'
            columns.append((qname, coltype))
        return columns

    def extract_columns_from_json(self, path):
        with open(path, 'r', encoding="utf-8") as f:
            form = json.load(f)
        fields = []
        if 'survey' in form:
            fields = [q.get('name') for q in form['survey'] if 'name' in q and q.get('type') and 'note' not in q.get('type')]
        elif 'children' in form:
            fields = [q.get('name') for q in form['children'] if 'name' in q and q.get('type') and 'note' not in q.get('type')]
        else:
            fields = list(form.keys())
        return [(f, 'NVARCHAR(MAX)') for f in fields if f]

    def show_create_sql(self):
        if not self.form_columns or not self.table_input.text().strip():
            QMessageBox.warning(self, "Missing Info", "Upload survey form & specify table name.")
            return
        self.table_name = self.table_input.text().strip()
        col_defs = ",\n    ".join([f"[{col}] {dtype}" for col, dtype in self.form_columns])
        create_stmt = f"CREATE TABLE [{self.table_name}] (\n    {col_defs}\n);"
        self.sql_text.setPlainText(create_stmt)
        with open("create_table.sql", "w", encoding='utf-8') as f:
            f.write(create_stmt)
        QMessageBox.information(self, "CREATE TABLE Ready", "SQL created. Please copy, paste, and execute it in your SQL tool.\n\nOnce done, click 'Check Table Exists'.")

    def check_table(self):
        table = self.table_input.text().strip()
        if not self.db_conn:
            QMessageBox.warning(self, "Not connected", "Connect to a database first!")
            return
        try:
            cur = self.db_conn.cursor()
            cur.execute(f"SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?", table)
            exists = cur.fetchone() is not None
            if exists:
                QMessageBox.information(self, "Table Exists", f"Table '{table}' found.")
                self.map_btn.setEnabled(bool(self.kobo_token))
            else:
                QMessageBox.warning(self, "Table Not Found", f"Table '{table}' does not exist in database {self.chosen_db}.")
                self.map_btn.setEnabled(False)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ----------- KOBO API LOGIN LOGIC -----------
    def kobo_login(self):
        username = self.kobo_username_input.text().strip()
        password = self.kobo_password_input.text().strip()
        if not username or not password:
            QMessageBox.warning(self, "Kobo", "Please enter Kobo username and password.")
            return
        try:
            resp = requests.post("https://kf.kobotoolbox.org/token/", auth=(username, password), timeout=10)
            if resp.status_code == 200:
                self.kobo_token = resp.json().get('token', '')
                if self.kobo_token:
                    self.kobo_login_status.setText("Kobo login successful.")
                    self.kobo_login_status.setStyleSheet("color: green")
                    self.map_btn.setEnabled(True)
                    QMessageBox.information(self, "Kobo Login", "Kobo login successful! Token acquired.")
                else:
                    self.kobo_login_status.setText("Kobo login failed.")
                    self.kobo_login_status.setStyleSheet("color: red")
                    QMessageBox.warning(self, "Kobo Login", "Login failed: Could not retrieve token.")
            else:
                self.kobo_login_status.setText("Kobo login failed.")
                self.kobo_login_status.setStyleSheet("color: red")
                QMessageBox.warning(self, "Kobo Login", f"Login failed (HTTP {resp.status_code}). Check credentials.")
        except Exception as e:
            self.kobo_login_status.setText("Kobo login failed.")
            self.kobo_login_status.setStyleSheet("color: red")
            QMessageBox.critical(self, "Kobo Login Error", str(e))

    def map_and_start_sync(self):
        if not self.map_btn.isEnabled():
            QMessageBox.warning(self, "Setup", "Please check table exists and log in to Kobo.")
            return
        self.kobo_form_id = self.kobo_form_id_input.text().strip()
        if not self.kobo_token or not self.kobo_form_id:
            QMessageBox.warning(self, "Kobo Setup", "Kobo token and form ID are required!")
            return
        # Fetch and push all Kobo data once
        initial = self.fetch_and_push_kobo_data()
        if initial >= 0:
            QMessageBox.information(self, "Sync Enabled", f"Initial push done. Inserted {initial} records. Auto-sync will keep your SQL table updated every 5 minutes.")
            self.stop_sync_btn.setEnabled(True)
            self.sync_timer.start()
        else:
            QMessageBox.warning(self, "Sync failed", f"Could not push Kobo data.")

    def fetch_and_push_kobo_data(self):
        try:
            colnames = [col for col, _ in self.form_columns]
            url = f"https://kf.kobotoolbox.org/api/v2/assets/{self.kobo_form_id}/data/?format=json&ordering=_id"
            records, new_last = [], self.last_id
            headers = {'Authorization': f'Token {self.kobo_token}'}
            next_url = url
            while next_url:
                resp = requests.get(next_url, headers=headers, timeout=30)
                resp.raise_for_status()
                js = resp.json()
                batch = [rec for rec in js.get('results', []) if int(rec.get('_id', 0)) > self.last_id]
                if not batch:
                    break
                records.extend(batch)
                next_url = js.get('next')
            if not records:
                return 0
            df = pd.DataFrame(records)
            df = df[[c for c in colnames if c in df.columns]]
            cur = self.db_conn.cursor()
            placeholders = ','.join(['?'] * len(df.columns))
            columns = ','.join([f'[{c}]' for c in df.columns])
            for row in df.itertuples(index=False, name=None):
                cur.execute(f"INSERT INTO [{self.table_name}] ({columns}) VALUES ({placeholders})", row)
                if '_id' in df.columns:
                    new_last = max(new_last, int(getattr(row, f'_{df.columns.get_loc("_id")+1}') if hasattr(row, f'_{df.columns.get_loc("_id")+1}') else 0))
            self.db_conn.commit()
            if '_id' in df.columns and not df.empty:
                self.last_id = int(df['_id'].max())
            return len(df)
        except Exception as e:
            QMessageBox.critical(self, "Mapping error", str(e))
            return -1

    def run_sync_once(self):
        count = self.fetch_and_push_kobo_data()
        if count > 0:
            QMessageBox.information(self, "Auto Sync", f"Auto-synced {count} new record(s).")
        # else silent for no new data

    def stop_sync(self):
        self.sync_timer.stop()
        self.stop_sync_btn.setEnabled(False)
        QMessageBox.information(self, "Sync", "Auto-sync stopped.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = KoboSqlMapper()
    window.show()
    sys.exit(app.exec_())