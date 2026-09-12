import os
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor


class DatabaseHelper:
    def __init__(
        self,
        dbname: str = os.environ.get("DB_NAME"),
        user: str = os.environ.get("DB_USER"),
        password: str = os.environ.get("DB_PASSWORD"),
        host: str = os.environ.get("DB_HOST"),
        port: str = os.environ.get("DB_PORT"),
    ):
        self.connection_params = {
            "dbname": dbname,
            "user": user,
            "password": password,
            "host": host,
            "port": port,
        }
        self.conn = None
        self.cur = None

    def connect(self) -> None:
        """Establish database connection."""
        try:
            self.conn = psycopg2.connect(**self.connection_params)
            self.cur = self.conn.cursor(cursor_factory=RealDictCursor)
        except psycopg2.Error as e:
            raise Exception(f"Error connecting to database: {e}")

    def disconnect(self) -> None:
        """Close database connection."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def commit(self) -> None:
        """Commit changes to the database."""
        if self.conn:
            self.conn.commit()

    def _ensure_connection(self) -> None:
        if not self.conn or self.conn.closed:
            self.connect()

    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results."""
        try:
            self._ensure_connection()
            self.cur.execute(query, params)
            results = self.cur.fetchall()
            if not results:
                return []
            return [dict(row) for row in results]
        except psycopg2.Error as e:
            if self.conn:
                self.conn.rollback()
            raise Exception(f"Query execution error: {e}")

    def execute_query_with_count(self, query: str, params: Optional[Dict[str, Any]] = None) -> int:
        """Execute a SELECT query with COUNT(*) and return the count."""
        try:
            self._ensure_connection()
            query = query.strip()
            if query.lower().startswith("select"):
                query = f"SELECT COUNT(*) FROM ({query}) AS subquery"
            self.cur.execute(query, params)
            result = self.cur.fetchone()
            if not result:
                return 0
            return result["count"]
        except psycopg2.Error as e:
            if self.conn:
                self.conn.rollback()
            raise Exception(f"Query execution error: {e}")

    def execute_query_with_single_result(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Execute a SELECT query and return the first result."""
        try:
            self._ensure_connection()
            self.cur.execute(query, params)
            result = self.cur.fetchone()
            if not result:
                return None
            return dict(result)
        except psycopg2.Error as e:
            if self.conn:
                self.conn.rollback()
            raise Exception(f"Query execution error: {e}")

    def execute_limit_offset_query(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        params: Optional[Dict[str, Any]] = None,
    ):
        """Execute a SELECT query with limit and offset and return results."""
        try:
            self._ensure_connection()
            paginated_query = f"SELECT * FROM ({query}) AS sub LIMIT {limit} OFFSET {offset}"
            self.cur.execute(paginated_query, params)
            results = self.cur.fetchall()
            if not results:
                return []
            return [dict(row) for row in results]
        except psycopg2.Error as e:
            if self.conn:
                self.conn.rollback()
            raise Exception(f"Query execution error: {e}")

    def execute_limit_offset_query_with_count(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        params: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Execute a SELECT query with limit and offset and return total count."""
        try:
            self._ensure_connection()
            query = query.strip()
            if not query.lower().endswith(("limit", "offset")):
                if "limit" not in query.lower():
                    query += f" LIMIT {limit}"
                if "offset" not in query.lower():
                    query += f" OFFSET {offset}"
            count_query = f"SELECT COUNT(*) FROM ({query}) AS subquery"
            self.cur.execute(count_query, params)
            result = self.cur.fetchone()
            if not result:
                return 0
            return result["count"]
        except psycopg2.Error as e:
            if self.conn:
                self.conn.rollback()
            raise Exception(f"Query execution error: {e}")

    def execute_modification(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        autocommit: bool = False,
    ) -> int:
        """Execute INSERT, UPDATE, or DELETE query and return affected rows."""
        try:
            self._ensure_connection()
            self.cur.execute(query, params)
            if autocommit:
                self.conn.commit()
            return self.cur.rowcount
        except psycopg2.Error as e:
            if self.conn:
                self.conn.rollback()
            raise Exception(f"Modification error: {e}")

    def execute_modification_with_last_row_id(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        autocommit: bool = False,
    ) -> int:
        """Execute INSERT, UPDATE, or DELETE query and return the id from RETURNING clause."""
        try:
            self._ensure_connection()
            if not query.strip().lower().endswith("returning id"):
                query = query.strip() + " RETURNING id"
            self.cur.execute(query, params)
            result = self.cur.fetchone()
            if autocommit:
                self.conn.commit()
            return result["id"] if result else None
        except psycopg2.Error as e:
            if self.conn:
                self.conn.rollback()
            raise Exception(f"Modification error: {e}")

    def execute_modification_returning_one(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        autocommit: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Execute a modification query with RETURNING and return a single row."""
        try:
            self._ensure_connection()
            self.cur.execute(query, params)
            result = self.cur.fetchone()
            if autocommit:
                self.conn.commit()
            return dict(result) if result else None
        except psycopg2.Error as e:
            if self.conn:
                self.conn.rollback()
            raise Exception(f"Modification error: {e}")

    def check_duplicate_record(self, table_name: str, conditions: Dict[str, Any]) -> bool:
        """Check if a record already exists in the specified table."""
        try:
            self._ensure_connection()
            where_clause = " AND ".join([f"{k} = %({k})s" for k in conditions.keys()])
            query = f"SELECT EXISTS(SELECT 1 FROM {table_name} WHERE {where_clause})"
            self.cur.execute(query, conditions)
            result = self.cur.fetchone()
            return result["exists"] if result else False
        except psycopg2.Error as e:
            if self.conn:
                self.conn.rollback()
            raise Exception(f"Error checking for duplicate: {e}")

    def fetch_one(self, query, params=None):
        return self.execute_query_with_single_result(query, params)

    def fetch_all(self, query, params=None):
        return self.execute_query(query, params)

    def fetch_paginated(self, query, params=None, page=1, page_size=20):
        page = max(int(page or 1), 1)
        page_size = max(int(page_size or 20), 1)
        offset = (page - 1) * page_size
        rows = self.execute_limit_offset_query(query, page_size, offset, params)
        return {
            "page": page,
            "page_size": page_size,
            "rows": rows,
        }

    def insert(self, table, data: dict, returning="*"):
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        if returning:
            query += f" RETURNING {returning}"
        self.cur.execute(query, list(data.values()))
        result = self.cur.fetchone() if returning else None
        self.conn.commit()
        return result

    def update(self, table, id_column, id_value, data: dict, returning="*"):
        set_clause = ", ".join([f"{k} = %s" for k in data.keys()])
        query = f"UPDATE {table} SET {set_clause} WHERE {id_column} = %s"
        if returning:
            query += f" RETURNING {returning}"
        self.cur.execute(query, [*data.values(), id_value])
        result = self.cur.fetchone() if returning else None
        self.conn.commit()
        return result

    def delete(self, table, id_column, id_value):
        self.cur.execute(f"DELETE FROM {table} WHERE {id_column} = %s", (id_value,))
        self.conn.commit()

    def execute(self, query, params=None):
        return self.execute_modification(query, params)

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


Database = DatabaseHelper


def get_db_connection():
    helper = DatabaseHelper()
    helper.connect()
    return helper.conn
