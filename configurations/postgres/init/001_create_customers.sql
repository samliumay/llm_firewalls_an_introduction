CREATE TABLE IF NOT EXISTS customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(320) NOT NULL UNIQUE,
    phone_number VARCHAR(32),
    date_of_birth DATE,
    national_id VARCHAR(100) UNIQUE,
    street_address TEXT,
    city VARCHAR(100),
    postal_code VARCHAR(20),
    country_code CHAR(2),
    total_amount NUMERIC(19, 2) NOT NULL DEFAULT 0.00,
    currency_code CHAR(3) NOT NULL DEFAULT 'USD',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT customers_total_amount_nonnegative CHECK (total_amount >= 0),
    CONSTRAINT customers_country_code_uppercase CHECK (
        country_code IS NULL OR country_code = UPPER(country_code)
    ),
    CONSTRAINT customers_currency_code_uppercase CHECK (
        currency_code = UPPER(currency_code)
    )
);

COMMENT ON TABLE customers IS
    'Demonstration bank customers containing sensitive financial and personal data.';
COMMENT ON COLUMN customers.total_amount IS 'Sensitive financial data.';
COMMENT ON COLUMN customers.email IS 'Personally identifiable information (PII).';
COMMENT ON COLUMN customers.phone_number IS 'Personally identifiable information (PII).';
COMMENT ON COLUMN customers.date_of_birth IS 'Personally identifiable information (PII).';
COMMENT ON COLUMN customers.national_id IS 'Highly sensitive personally identifiable information.';
COMMENT ON COLUMN customers.street_address IS 'Personally identifiable information (PII).';

