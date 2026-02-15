# Product Requirements Document: Meeting-Buddy v2.0

**Project Name:** Meeting-Buddy
**Vision:** A privacy-first, proactive "Digital Co-Pilot" that transforms live audio and static documents into real-time intelligence.
**Core Philosophy:** Invisible, Proactive, and Personal.

---

## 1. Executive Summary
Meeting-Buddy is a macOS-native application that serves as a "Live Whisperer" during meetings. Unlike passive recording bots, it leverages a **Personal Knowledge Base** (ingested Markdown, PDFs, and Word docs) to provide proactive coaching and fact-checking via a non-intrusive companion interface.

## 2. Key Objectives
* **Proactive Intelligence:** Move from reactive "search-on-command" to automated "nudges" based on meeting context.
* **Deep Context:** Use existing user documentation to provide continuity across meetings.
* **Privacy-First:** Localized processing of sensitive audio and document data.
* **Zero-Friction UX:** Operates as a "Buddy" on a secondary screen or HUD, avoiding the "bot in the call" stigma.

---

## 3. Functional Requirements

### 3.1. The "Brain" (Knowledge Ingestion)
* **Static Ingestion:** Ability to parse and index `.md`, `.pdf`, and `.docx` files.
* **Dynamic Memory:** Automatically folds past meeting transcripts into the searchable knowledge graph.
* **RAG (Retrieval-Augmented Generation):** Local or secure API-based vector search to pull relevant facts in <2 seconds.

### 3.2. The "Whisperer" (Live UI/UX)
* **Companion HUD:** A dedicated window designed for secondary monitors or a transparent overlay.
* **Proactive Nudges:** The AI "pushes" information to the user without being asked if it detects:
    * **Contradictions:** "Participant said $X$, but your 'Project_Spec.pdf' says $Y$."
    * **Goal Gaps:** "You haven't mentioned the 'Timeline' yet (set as a meeting goal)."
    * **Contextual Facts:** "This person was also in the 'January Sync' where we discussed $Z$."
* **Live Transcription:** Real-time scrolling text with speaker identification.

### 3.3. Audio & Privacy
* **System Audio Capture:** High-fidelity loopback audio capture for any meeting platform (Zoom, Meet, Slack).
* **Local Processing:** Option to run inference via local LLMs (Ollama/Apple MLX) for maximum privacy.

---

## 4. Feature Roadmap

| Priority | Feature Group | Description | Status |
| :--- | :--- | :--- | :--- |
| **High** | **Proactive Logic** | AI-driven "interruption" logic to nudge users with facts from ingested docs. | *In Development* |
| **High** | **Multi-Doc RAG** | Enhancing the search across diverse file formats (MD, PDF, Word) for live context. | *In Development* |
| **Medium** | **Vibe/Sentiment** | Visual "Heat Map" of meeting energy and speaker sentiment. | *Planned* |
| **Medium** | **Voice-to-Audio Link** | Click any transcript line to replay that specific audio snippet. | *Planned* |
| **Low** | **Calendar Sync** | Auto-naming and doc-loading based on macOS Calendar events. | *Backlog* |
| **Low** | **Smart Screen** | Automated screenshot/OCR capture of shared slides. | *Backlog* |

---

## 5. Technical Requirements & Logic
* **Agentic Routing:** A controller that monitors the live transcript and decides when a "Whisper" is high-confidence enough to display.
* **Latency Target:** Transcription-to-Nudge latency must be under **2.5 seconds** to remain conversationally relevant.
* **Storage:** Vector embeddings and transcripts must be stored locally in an encrypted database.

---

## 6. Target User Journey
1.  **Ingest:** User drags a "Client Contract" PDF and "Internal Notes" MD file into Meeting-Buddy.
2.  **Live Meeting:** User joins a call; the Companion App wakes up on the second monitor.
3.  **The Nudge:** When the client mentions a 20% discount, Meeting-Buddy flashes a subtle red border: *"Contract says max discount is 15%."*
4.  **Sync:** After the call, the meeting summary is automatically appended to the "Client History" knowledge base.
