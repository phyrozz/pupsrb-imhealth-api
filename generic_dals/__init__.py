from utils.db import DatabaseHelper
from psycopg2.extras import RealDictCursor


class BaseDAL:
    def __init__(self, conn, table: str):
        if isinstance(conn, DatabaseHelper):
            self.db = conn
        else:
            self.db = DatabaseHelper()
            self.db.conn = conn
            self.db.cur = conn.cursor(cursor_factory=RealDictCursor)
        self.table = table

    def _fetch_one(self, query: str, params=None):
        return self.db.fetch_one(query, params)

    def _fetch_all(self, query: str, params=None):
        return self.db.fetch_all(query, params)

    def _execute_write(self, query: str, params=None):
        return self.db.execute_modification_returning_one(query, params, autocommit=True)

    def find_by_id(self, id_column: str, id_value):
        return self._fetch_one(
            f"SELECT * FROM {self.table} WHERE {id_column} = %s",
            (id_value,),
        )

    def insert(self, data: dict):
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        return self._execute_write(
            f"INSERT INTO {self.table} ({columns}) VALUES ({placeholders}) RETURNING *",
            list(data.values()),
        )

    def update(self, id_column: str, id_value, data: dict):
        set_clause = ", ".join([f"{k} = %s" for k in data.keys()])
        return self._execute_write(
            f"UPDATE {self.table} SET {set_clause} WHERE {id_column} = %s RETURNING *",
            [*data.values(), id_value],
        )

    def delete(self, id_column: str, id_value):
        self.db.execute_modification(
            f"DELETE FROM {self.table} WHERE {id_column} = %s",
            (id_value,),
            autocommit=True,
        )
