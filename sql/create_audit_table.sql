USE CurrencyETL;
GO

IF OBJECT_ID('dbo.etl_run_log', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_run_log (
        run_id            INT IDENTITY(1,1) PRIMARY KEY,
        pipeline_name     NVARCHAR(100)  NOT NULL,
        started_at        DATETIME2(0)   NOT NULL,
        ended_at          DATETIME2(0)   NULL,
        duration_seconds  DECIMAL(10, 2) NULL,
        status            NVARCHAR(20)   NOT NULL,   -- RUNNING, SUCCESS, FAILED
        rows_extracted    INT            NULL,
        rows_transformed  INT            NULL,
        rows_loaded_clean INT            NULL,
        error_stage       NVARCHAR(50)   NULL,       -- extract, transform, load
        error_message     NVARCHAR(MAX)  NULL,
        host_name         NVARCHAR(100)  NULL,
        triggered_by      NVARCHAR(50)   NULL         -- manual, scheduler
    );

    CREATE INDEX IX_etl_run_log_started_at 
        ON dbo.etl_run_log (started_at DESC);
END
GO