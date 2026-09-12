from generic_dals import BaseDAL


class ProgramsDAL(BaseDAL):
    def __init__(self, conn):
        super().__init__(conn, "public.programs")

    def list_programs(self, query: str, page_size: int, page: int):
        """Return one stable page of programs and the matching total."""
        where_clause = ""
        params = ()
        if query:
            where_clause = " WHERE initial ILIKE %s ESCAPE E'\\\\' OR name ILIKE %s ESCAPE E'\\\\'"
            escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped_query}%"
            params = (pattern, pattern)

        count_row = self._fetch_one(
            f"SELECT COUNT(*) AS total FROM public.programs{where_clause}", params
        )
        total = int(count_row["total"] if count_row else 0)
        offset = (page - 1) * page_size
        items = self._fetch_all(
            "SELECT id, initial, name FROM public.programs"
            f"{where_clause} ORDER BY initial, name, id LIMIT %s OFFSET %s",
            params + (page_size, offset),
        )
        return {"items": items, "total": total}
