-- 0001 guessed vector(1536) (a common OpenAI embedding size) before a
-- provider was chosen. We're starting with Gemini's text-embedding-004,
-- which outputs 768 dimensions. Safe to ALTER since no rows exist yet;
-- revisit if/when a second embedding provider needs a different size
-- (options then: a second column, or a separate table per model).
alter table knowledge_chunks alter column embedding type vector(768);
