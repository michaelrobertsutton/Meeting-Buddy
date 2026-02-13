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

### Error response
```json
{ "type": "response", "id": "1", "success": false, "error": "Unknown command" }
```

### Backend → UI: Events
Events are pushed without an id.

## Snapshot / Update payload
The backend periodically sends:
- `type: "snapshot"` on initial connect
- `type: "update"` on transcript/question changes

### Required fields
- `type` ("snapshot" | "update")
- `protocol_version` (integer, currently `1`)
- `version` (monotonic integer)

### Common fields (may be absent)
- `segments` (transcript segments)
- `active_question`
- `question_history`
- `manual_question` (boolean)
- `synthesis_searching` (boolean)
- `active_answer`
- `qa_history`
- `pinned`

### Example (snapshot/update)
```json
{
  "type": "update",
  "protocol_version": 1,
  "version": 42,
  "active_question": "What is our launch timeline?",
  "manual_question": false,
  "synthesis_searching": false,
  "segments": [
    {"start_time": 0.0, "end_time": 2.1, "text": "…"}
  ],
  "active_answer": {
    "one_liner": "…",
    "bullets": ["…"],
    "citations": []
  }
}
```

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

### Example: answer_update
```json
{
  "type": "answer_update",
  "active_answer": {
    "one_liner": "One sentence answer",
    "bullets": ["Evidence-backed bullet"],
    "best_practice_bullets": [],
    "clarifiers": [],
    "citations": [
      {"doc": "Doc.pdf", "section": "Intro", "page": 1, "quote": "…"}
    ],
    "confidence": 0.8
  }
}
```

---

## Protocol versioning
- `protocol_version` is included on `snapshot`/`update` and is currently `1`.
- Clients should ignore unknown fields.
- Backends should not remove fields without bumping protocol_version.
