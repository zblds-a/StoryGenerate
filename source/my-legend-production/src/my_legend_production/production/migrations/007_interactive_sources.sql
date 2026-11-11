-- Confirmed immutable session source registration. Existing jobs are untouched.
CREATE TABLE IF NOT EXISTS interactive_story_sources (
    owner_id text NOT NULL,
    session_id text NOT NULL,
    story_version_id text NOT NULL,
    kind text NOT NULL,
    sha256 text NOT NULL,
    metadata jsonb NOT NULL,
    PRIMARY KEY(owner_id, session_id, story_version_id, kind),
    UNIQUE(owner_id, story_version_id, kind, sha256)
);
