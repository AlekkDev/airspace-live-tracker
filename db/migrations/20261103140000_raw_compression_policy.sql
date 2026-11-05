-- migrate:up
-- Merged after the M1 backlog drain (docs/03-data-model.md#rawstate_vectors-hypertable).
SELECT add_compression_policy('raw.state_vectors', interval '2 days');

-- migrate:down
