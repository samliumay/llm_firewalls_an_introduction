-- All records below are fictional and intended only for local demonstrations.
INSERT INTO customers (
    first_name,
    last_name,
    email,
    phone_number,
    date_of_birth,
    national_id,
    street_address,
    city,
    postal_code,
    country_code,
    total_amount,
    currency_code
)
VALUES
    (
        'Ada',
        'Demo',
        'ada.demo@example.test',
        '+1-555-0101',
        DATE '1988-04-12',
        'DEMO-NID-1001',
        '101 Example Avenue',
        'Testville',
        '10001',
        'US',
        12540.75,
        'USD'
    ),
    (
        'Mert',
        'Sample',
        'mert.sample@example.test',
        '+90-555-000-0102',
        DATE '1993-09-23',
        'DEMO-NID-1002',
        '42 Sandbox Street',
        'Istanbul',
        '34000',
        'TR',
        82450.00,
        'TRY'
    ),
    (
        'Lin',
        'Example',
        'lin.example@example.test',
        '+44-7700-900103',
        DATE '1979-01-30',
        'DEMO-NID-1003',
        '7 Mock Lane',
        'London',
        'SW1A 1AA',
        'GB',
        3100.20,
        'GBP'
    )
ON CONFLICT (email) DO NOTHING;
