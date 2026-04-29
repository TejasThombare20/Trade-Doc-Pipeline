-- Add file_url columns for SAS/signed URL caching.
-- Drop extracted_rules column: rules now live in extractions.tool_output only.

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS file_url TEXT,
    ADD COLUMN IF NOT EXISTS file_url_expires_at TIMESTAMPTZ;

-- extracted_rules column is no longer written by the pipeline.
-- Rules are always read from extractions.tool_output for rule_book documents.
ALTER TABLE documents DROP COLUMN IF EXISTS extracted_rules;
