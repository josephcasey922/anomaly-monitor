-- ONLY FOR LOCAL SYNTHETIC DEMO. Never reuse demo passwords in production.
CREATE TABLE IF NOT EXISTS public.daily_metrics (
    "BusinessDate" DATE NOT NULL,
    "StoreID" TEXT NOT NULL,
    "Washes" INTEGER,
    "NetRevenue" NUMERIC(14,2),
    "LaborHours" NUMERIC(14,2),
    "OperatingIncome" NUMERIC(14,2),
    "Opportunities" INTEGER,
    "Conversions" INTEGER,
    "Region" TEXT,
    "DataSource" TEXT,
    PRIMARY KEY ("BusinessDate", "StoreID")
);
CREATE ROLE anomaly_reader LOGIN PASSWORD 'demo_reader_LOCAL_ONLY';
GRANT CONNECT ON DATABASE anomaly_demo TO anomaly_reader;
GRANT USAGE ON SCHEMA public TO anomaly_reader;
GRANT SELECT ON TABLE public.daily_metrics TO anomaly_reader;
