"""Schema constants that must be changed through a database migration."""

# PostgreSQL vector columns have a fixed dimension. Changing this value requires
# a migration and a complete re-embedding of the concept search projection.
EMBEDDING_DIMENSIONS = 1536
