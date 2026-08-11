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

CREATE INDEX IF NOT EXISTS idx_time_entries_spent_on ON time_entries(spent_on);
CREATE INDEX IF NOT EXISTS idx_time_entries_project ON time_entries(project_id);
CREATE INDEX IF NOT EXISTS idx_time_entries_ticket ON time_entries(ticket_id);
CREATE INDEX IF NOT EXISTS idx_tickets_validity ON tickets(valid_from, valid_to);
CREATE UNIQUE INDEX IF NOT EXISTS idx_time_entries_source_row
    ON time_entries(source, source_row)
    WHERE source_row IS NOT NULL;

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
