CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS categories (
    code text PRIMARY KEY,
    name text NOT NULL,
    description text
);

CREATE TABLE IF NOT EXISTS projects (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    name text NOT NULL UNIQUE,
    normalized_name text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transports (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    name text NOT NULL UNIQUE,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS app_users (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    username text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    role text NOT NULL DEFAULT 'viewer',
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT app_users_role_check CHECK (role IN ('admin', 'editor', 'viewer'))
);

CREATE TABLE IF NOT EXISTS tickets (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id text NOT NULL UNIQUE,
    project_id uuid REFERENCES projects(id),
    subject text,
    is_overhead boolean NOT NULL DEFAULT false,
    valid_from timestamptz,
    valid_to timestamptz,
    source_period text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS time_entries (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    spent_on date NOT NULL,
    started_at time,
    ended_at time,
    duration_hours numeric(8, 2) NOT NULL,
    category_code text REFERENCES categories(code),
    description text NOT NULL,
    ticket_id uuid REFERENCES tickets(id),
    project_id uuid REFERENCES projects(id),
    transport_id uuid REFERENCES transports(id),
    km numeric(10, 2),
    overlap_hours numeric(8, 2) DEFAULT 0,
    redmine_time text,
    reported_status text,
    source text NOT NULL DEFAULT 'manual',
    source_row integer,
    raw_text text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS voice_inputs (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    original_text text NOT NULL,
    parsed_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'draft',
    created_entry_id uuid REFERENCES time_entries(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS import_batches (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_file text NOT NULL,
    source_checksum text,
    imported_rows integer NOT NULL DEFAULT 0,
    skipped_rows integer NOT NULL DEFAULT 0,
    error_rows integer NOT NULL DEFAULT 0,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);

CREATE TABLE IF NOT EXISTS fuel_vehicles (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    code text NOT NULL UNIQUE,
    name text NOT NULL UNIQUE,
    is_active boolean NOT NULL DEFAULT false,
    sort_order integer NOT NULL DEFAULT 0,
    source_sheets jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fuel_entries (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    vehicle_id uuid NOT NULL REFERENCES fuel_vehicles(id),
    purchased_on date NOT NULL,
    purchased_at time,
    station text,
    fuel_type text,
    odometer_km numeric(12, 2),
    liters numeric(10, 2),
    total_price_vat numeric(12, 2),
    total_price_no_vat numeric(12, 2),
    price_per_liter numeric(10, 2),
    trip_km numeric(10, 2),
    full_tank boolean,
    average_consumption numeric(8, 2),
    note text,
    receipt_photo_path text,
    dashboard_photo_path text,
    source text NOT NULL DEFAULT 'manual',
    source_sheet text,
    source_row integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_time_entries_spent_on ON time_entries(spent_on);
CREATE INDEX IF NOT EXISTS idx_time_entries_project ON time_entries(project_id);
CREATE INDEX IF NOT EXISTS idx_time_entries_ticket ON time_entries(ticket_id);
CREATE INDEX IF NOT EXISTS idx_tickets_validity ON tickets(valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_fuel_entries_vehicle_date ON fuel_entries(vehicle_id, purchased_on);
CREATE UNIQUE INDEX IF NOT EXISTS idx_time_entries_source_row
    ON time_entries(source, source_row)
    WHERE source_row IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_fuel_entries_source_row
    ON fuel_entries(source, source_sheet, source_row)
    WHERE source = 'excel' AND source_sheet IS NOT NULL AND source_row IS NOT NULL;

INSERT INTO categories (code, name, description) VALUES
    ('S', 'Soukrome', 'Soukrome aktivity'),
    ('V', 'Vzdelavani', 'Vzdelavani a rozvoj'),
    ('D', 'Doprava', 'Doprava'),
    ('A', 'ABRA', 'ABRA aktivity'),
    ('R', 'Rozvoj firmy', 'Rozvoj firmy'),
    ('RP', 'Rozvojove projekty', 'Rozvojove projekty'),
    ('F', 'Firma', 'Firemni aktivity'),
    ('IT', 'IT', 'IT aktivity')
ON CONFLICT (code) DO NOTHING;

INSERT INTO transports (name) VALUES
    ('Volvo XC90'),
    ('vlak'),
    ('autobus'),
    ('MHD')
ON CONFLICT (name) DO NOTHING;

INSERT INTO fuel_vehicles (code, name, is_active, sort_order, source_sheets) VALUES
    ('volvo-xc90', 'Volvo', true, 1, '["EL6 14DE XC90"]'::jsonb),
    ('skoda-felicie', 'Skoda Felicie', false, 2, '["ZLI 89-51 Natural 95", "ZLI 89-51 LPG"]'::jsonb),
    ('audi-a6', 'Audi A6', false, 3, '["5Z0 9004 AUDI"]'::jsonb),
    ('vw-passat', 'VW Passat', false, 4, '["2Z4 3277 Passat"]'::jsonb),
    ('bmw', 'BMW', false, 5, '["6AP 0033 BMW"]'::jsonb)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    source_sheets = EXCLUDED.source_sheets;
