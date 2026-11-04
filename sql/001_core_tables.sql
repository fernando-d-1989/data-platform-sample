-- The shared shape. Every client uses these tables, separated by client_id.

-- Bronze: exactly what arrived, never edited.
CREATE TABLE bronze_raw (
    id bigserial PRIMARY KEY,
    source text NOT NULL,
    payload jsonb NOT NULL,
    payload_hash text GENERATED ALWAYS AS (md5(payload::text)) STORED,
    loaded_at timestamptz DEFAULT now(),
    last_seen_at timestamptz DEFAULT now(), -- the only column that ever changes: when the source last sent this version
    UNIQUE (source, payload_hash)          -- the same record twice is one row; a changed record is a new one
);

-- Silver: clean, one shape for every client. Updated by key, because it holds things
-- that can't be rebuilt, such as corrections people make in the app.
CREATE TABLE silver_person (
    client_id uuid NOT NULL,
    external_id text NOT NULL,
    email text,
    phone text,
    channel text NOT NULL DEFAULT 'unknown',
    procedure text,
    city text,
    advisor text,
    created_on date,
    metadata jsonb DEFAULT '{}',          -- descriptive extras; anything a screen filters on gets a real column
    PRIMARY KEY (client_id, external_id)
);

CREATE TABLE silver_operation (
    client_id uuid NOT NULL,
    external_id text NOT NULL,
    person_external_id text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('assessment', 'surgery')),
    status text NOT NULL CHECK (status IN ('attended', 'no_show', 'booked', 'done', 'scheduled')),
    date date NOT NULL,
    confirmed boolean,
    value numeric(12, 2),
    metadata jsonb DEFAULT '{}',
    PRIMARY KEY (client_id, external_id),  -- this stops duplicates, even if the loader has a bug
    FOREIGN KEY (client_id, person_external_id) REFERENCES silver_person (client_id, external_id)
);

-- Each time a person wrote, called or answered. The model reads this.
CREATE TABLE silver_engagement (
    client_id uuid NOT NULL,
    person_external_id text NOT NULL,
    date date NOT NULL,
    PRIMARY KEY (client_id, person_external_id, date),
    FOREIGN KEY (client_id, person_external_id) REFERENCES silver_person (client_id, external_id)
);
