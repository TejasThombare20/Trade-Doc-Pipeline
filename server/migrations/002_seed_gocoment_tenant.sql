-- Merge tenants and customers: they are the same concept.
-- Keep `tenants` (used by auth/JWT/sessions), drop `customers`.

-- 1. Drop the unique-active-rule-book index (references customer_id).
DROP INDEX IF EXISTS idx_documents_one_active_rule_book;

-- 2. Drop customer-based indexes on documents.
DROP INDEX IF EXISTS idx_documents_tenant_customer;

-- 3. Drop the customer_id column from documents.
ALTER TABLE documents DROP COLUMN IF EXISTS customer_id;

-- 4. Create a new unique index: one active rule_book per tenant.
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_one_active_rule_book
    ON documents(tenant_id)
    WHERE type = 'rule_book' AND is_active = TRUE;

-- 5. Drop the customers table.
DROP TABLE IF EXISTS customers;

-- 6. Seed the goComent tenant for local development.
INSERT INTO tenants (name, slug)
VALUES ('goComent', 'gocoment')
ON CONFLICT (slug) DO NOTHING;
