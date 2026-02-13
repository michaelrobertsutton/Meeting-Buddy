# Meeting Buddy Protocol (WebSocket)

This document describes the **local WebSocket protocol** used between the UI (Tauri) and the backend.

- Default URL: `ws://localhost:8765`
- Transport: JSON messages

## Message types

### UI → Backend: Command
```json
{ "id": "1", "command": "get_settings", "...params": "..." }
```

### Backend → UI: Response
```json
{ "type": "response", "id": "1", "success": true, "data": { } }
```

### Backend → UI: Events
Events are pushed without an id.

## Snapshot / Update payload
The backend periodically sends:
- `type: "snapshot"` on initial connect
- `type: "update"` on transcript/question changes

Common fields:
- `version` (monotonic integer)
- `segments` (transcript segments)
- `active_question`
- `question_history`
- `manual_question` (boolean)
- `synthesis_searching` (boolean)
- `active_answer`
- `qa_history`
- `pinned`

## Commands (current)

### Settings / Auth
- `get_settings`
- `set_api_key { key }`
- `start_login`
- `login_status`
- `logout`

### Projects
- `list_projects`
- `create_project { name }`
- `switch_project { name }`
- `delete_project { name }`

### Documents / Ingest
- `list_docs`
- `ingest_files { paths: string[] }`
- `delete_doc { title }`
- `get_doc_meta`
- `update_doc_meta { title, description?, priority? }`

### Meeting UX
- `select_question { text? }`  (omit/empty to resume auto)
- `set_question { text }` (free-form override; empty clears)

### Prep mode
- `generate_prep_questions { count? }`
- `get_prep_results`
- `add_prep_question { text }`

### Pins
- `get_pinned`
- `pin_answer { question?, answer? }`
- `unpin_answer { id? | question? }`

### Export
- `export_session { format: "markdown"|"json", path }`

## Events
- `ingest_progress { current, total, file }`
- `ingest_complete { total_chunks, file_count, errors }`
- `synthesis_searching { question }`
- `synthesis_error { error }`
- `answer_update { active_answer }`
- `pinned_update { pinned }`
- `auth_complete { oauth_status }`
- `auth_error { error }`
- `auth_logout`

---

## Future: protocol versioning
Add `protocol_version` on snapshot/update to allow non-breaking evolution.
