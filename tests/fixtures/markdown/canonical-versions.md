# Canonical Versions

## Source Identity

The keyanchor rule treats canonical_key as the stable source identity.
Content hash determines duplicate detection and whether a new source version is created.

## Path Fallback

When canonical_key is absent, the fallback uses knowledge_type plus normalized absolute path.
