USE CurrencyETL;
GO

-- Market rates from Frankfurter (ECB source)
IF OBJECT_ID('dbo.market_currency_rates', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.market_currency_rates (
        market_id       INT IDENTITY(1,1) PRIMARY KEY,
        base_currency   NVARCHAR(10)   NOT NULL,   -- always 'EUR' for Frankfurter
        quote_currency  NVARCHAR(10)   NOT NULL,   -- USD, GBP, JPY, CHF, CNY
        rate            DECIMAL(18, 6) NOT NULL,   -- units of quote per 1 base
        rate_date       DATE           NOT NULL,
        source_system   NVARCHAR(50)   NOT NULL DEFAULT 'FRANKFURTER_ECB',
        loaded_at       DATETIME2(0)   NOT NULL DEFAULT SYSDATETIME(),
        CONSTRAINT UQ_market_rate UNIQUE (base_currency, quote_currency, rate_date)
    );
END
GO

-- Divergence analytics (CBU implied vs Market actual)
IF OBJECT_ID('dbo.currency_divergence', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.currency_divergence (
        divergence_id       INT IDENTITY(1,1) PRIMARY KEY,
        rate_date           DATE           NOT NULL,
        base_currency       NVARCHAR(10)   NOT NULL,   -- 'EUR'
        quote_currency      NVARCHAR(10)   NOT NULL,   -- USD, GBP, etc.
        cbu_implied_rate    DECIMAL(18, 6) NULL,
        market_rate         DECIMAL(18, 6) NULL,
        absolute_divergence DECIMAL(18, 6) NULL,
        pct_divergence      DECIMAL(10, 4) NULL,
        loaded_at           DATETIME2(0)   NOT NULL DEFAULT SYSDATETIME(),
        CONSTRAINT UQ_divergence UNIQUE (rate_date, base_currency, quote_currency)
    );
END
GO