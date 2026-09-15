USE CurrencyETL;
GO

IF OBJECT_ID('dbo.clean_currency_rates', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.clean_currency_rates (
        clean_id          INT IDENTITY(1,1) PRIMARY KEY,
        currency_code     NVARCHAR(10)   NOT NULL,
        currency_name     NVARCHAR(100)  NULL,
        nominal           INT            NULL,
        rate_uzs          DECIMAL(18, 4) NULL,
        diff_uzs          DECIMAL(18, 4) NULL,
        rate_date         DATE           NOT NULL,
        loaded_at         DATETIME2(0)   NOT NULL DEFAULT SYSDATETIME(),
        rate_per_unit     DECIMAL(18, 6) NULL,
        change_direction  NVARCHAR(20)   NULL,
        is_appreciated    BIT            NULL,
        is_depreciated    BIT            NULL,
        CONSTRAINT UQ_clean_currency_date UNIQUE (currency_code, rate_date)
    );
END
GO