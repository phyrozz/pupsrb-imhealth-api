import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from generic_dals.cron_dal import CronDAL
from utils.db import get_db_connection


logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def insert_assessment_trends(conn):
    """Snapshot cumulative changes between students' consecutive assessments."""
    dal = CronDAL(conn)
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    next_day_start = day_start + timedelta(days=1)

    dal.lock_trend_snapshot()
    counts = dal.get_scenario_change_counts()
    dal.insert_mental_health_uptrend(counts["increase_count"], day_start, next_day_start)
    dal.insert_mental_health_downtrend(counts["decrease_count"], day_start, next_day_start)

    dal.commit()
    log.info("insert_assessment_trends complete")


def main():
    conn = None
    try:
        task_event = os.environ.get("TASK_EVENT", "{}")
        event = json.loads(task_event)
        task = event.get("task")
        if task not in (None, "insert_assessment_trends"):
            raise ValueError(f"Unknown cron task: {task}")

        conn = get_db_connection()

        insert_assessment_trends(conn)

        log.info(json.dumps({"event": "complete", "task": task, "timestamp": datetime.now(timezone.utc).isoformat()}))

    except Exception as e:
        log.error(json.dumps({"event": "error", "error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}))
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
