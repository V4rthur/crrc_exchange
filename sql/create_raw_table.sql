USE CurrencyETL;
GO

IF OBJECT_ID('dbo.raw_currency_rates', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.raw_currency_rates (
        raw_id         INT IDENTITY(1,1) PRIMARY KEY,
        ccy            NVARCHAR(10)   NOT NULL,
        ccy_nm_uz      NVARCHAR(100)  NULL,
        ccy_nm_ru      NVARCHAR(100)  NULL,
        ccy_nm_en      NVARCHAR(100)  NULL,
        nominal        INT            NULL,
        rate           DECIMAL(18, 4) NULL,
        diff           DECIMAL(18, 4) NULL,
        [date]         DATE           NULL,
        loaded_at      DATETIME2(0)   NOT NULL DEFAULT SYSDATETIME(),
        source_system  NVARCHAR(50)   NOT NULL DEFAULT 'CBU_JSON',
        raw_json       NVARCHAR(MAX)  NULL
    );

    CREATE INDEX IX_raw_currency_rates_ccy_date
        ON dbo.raw_currency_rates (ccy, [date]);
END
GO