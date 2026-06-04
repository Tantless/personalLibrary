# Search Ranking

## PostgreSQL FTS

The rankanchor example verifies PostgreSQL full text rank plus title boost.
Title matches should sort ahead of body-only matches when the query is exact.

## No Recency Boost

MVP ranking does not add recency weight by default.
