USE CurrencyETL;
GO

ALTER TABLE dbo.clean_currency_rates ADD 
    diff_zscore        DECIMAL(10, 4) NULL,
    ma7_rate           DECIMAL(18, 6) NULL,
    ma7_deviation_pct  DECIMAL(10, 4) NULL,
    is_anomaly         BIT            NULL,
    anomaly_reason     NVARCHAR(100)  NULL;
GO