import socket
from datetime import datetime
from sqlalchemy import text

from config import get_engine

def start_run(pipeline_name: str, triggered_by: str = "manual") -> int:
    """Insert a new run record with status=RUNNING. Returns run_id."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO dbo.etl_run_log 
                    (pipeline_name, started_at, status, host_name, triggered_by)
                OUTPUT INSERTED.run_id
                VALUES 
                    (:pipeline_name, :started_at, 'RUNNING', :host_name, :triggered_by)
            """),
            {
                "pipeline_name": pipeline_name,
                "started_at": datetime.now(),
                "host_name": socket.gethostname(),
                "triggered_by": triggered_by,
            },
        )
        run_id = result.scalar()
    return run_id


def finish_run(
    run_id: int,
    status: str,
    rows_extracted: int = None,
    rows_transformed: int = None,
    rows_loaded_clean: int = None,
    error_stage: str = None,
    error_message: str = None,
):
    """Update run record with final status and metrics."""
    engine = get_engine()
    ended_at = datetime.now()

    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE dbo.etl_run_log
                SET 
                    ended_at = :ended_at,
                    duration_seconds = DATEDIFF_BIG(MILLISECOND, started_at, :ended_at) / 1000.0,
                    status = :status,
                    rows_extracted = :rows_extracted,
                    rows_transformed = :rows_transformed,
                    rows_loaded_clean = :rows_loaded_clean,
                    error_stage = :error_stage,
                    error_message = :error_message
                WHERE run_id = :run_id
            """),
            {
                "run_id": run_id,
                "ended_at": ended_at,
                "status": status,
                "rows_extracted": rows_extracted,
                "rows_transformed": rows_transformed,
                "rows_loaded_clean": rows_loaded_clean,
                "error_stage": error_stage,
                "error_message": (error_message[:4000] if error_message else None),
            },
        )