# Raw Archive Policy

## Version Trace

The archiveanchor rule stores immutable raw bytes for every source version.
Each archived file must support read back from source id, version id, and locator.

## Manual Backup

MVP backup is manual: preserve the Docker volume and the local raw archive path.
