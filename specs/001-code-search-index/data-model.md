# Data Model

## Entities

### Repository
- Fields: id, name, git_url, default_branch, auth_type, auth_credential_ref, access_state, created_at, updated_at.
- Relationships: has many Branch, has many Artifact, has many Notification, has many Query.
- Validation: name required; git_url valid and reachable; default_branch required.

### Branch
- Fields: id, repository_id, name, is_default, tracked, last_indexed_at, last_notification_at, freshness_status, backlog_size.
- Relationships: belongs to Repository; has many Artifact, IndexRecord.
- Validation: name required; tracked boolean; freshness_status in [fresh, stale, error, pending].

### Artifact
- Fields: id, repository_id, branch_id, path, file_type, size_bytes, parse_status, has_line_map, last_seen_commit, last_indexed_at.
- Relationships: belongs to Repository and Branch; has many IndexRecord.
- Validation: path unique per repo+branch; file_type enum (code, config, doc, pdf, binary, other); parse_status in [parsed, skipped, failed].

### IndexRecord
- Fields: id, artifact_id, repository_id, branch_id, chunk_id, content, embedding_vector, line_start, line_end, language, created_at.
- Relationships: belongs to Artifact, Repository, Branch.
- Validation: line_start <= line_end; embedding_vector present for text content.

### Query
- Fields: id, user_id, scope_repositories, scope_branches, query_text, response_text, response_citations, response_latency_ms, created_at.
- Relationships: belongs to User; references IndexRecord citations.
- Validation: scope_repositories non-empty; branch scope optional but validated.

### Notification
- Fields: id, repository_id, branch_id, source (webhook, schedule), event_id, received_at, processed_at, status.
- Relationships: belongs to Repository and Branch; may enqueue ingestion jobs.
- Validation: source enum; status in [pending, processing, done, error].

## State Notes
- Backlog tracking: backlog_size on Branch to capture queued jobs; used for alerts.
- Access control: repository-level ACL references users/teams (not modeled here) used to filter queries and listings.
