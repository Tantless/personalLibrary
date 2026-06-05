# Search Review

User: How should filters work in search_knowledge?

Assistant: The filteranchor check uses knowledge_type, canonical_key, and top_k filters without changing ranking logic.

User: Should ranking include embeddings?

Assistant: MVP uses PostgreSQL full text search only.
