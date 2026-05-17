https://roadmap.sh/projects/markdown-note-taking-app


# Markdown Note-Taking App

A RESTful API service for managing Markdown notes, with grammar checking and HTML rendering.

## Features

| # | Feature | Endpoint |
|---|---------|----------|
| 1 | Check grammar of a note | `POST /notes/grammar` |
| 2 | Save a new note | `POST /notes` |
| 3 | List all saved notes | `GET /notes` |
| 4 | Get HTML-rendered note | `GET /notes/{note_id}` |
| 5 | Get raw markdown | `GET /notes/{note_id}/raw` |
| 6 | Delete a note | `DELETE /notes/{note_id}` |
| — | Swagger / ReDoc | `GET /docs` |

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the server
uvicorn main:app --reload --port 5040

# 3. Open interactive docs
open http://localhost:5040/docs
```

## API Usage

### Save a note
```bash
curl -X POST http://localhost:5040/notes \
  -H "Content-Type: application/json" \
  -d '{"name":"my-notes.md","content":"# Title\n\nSome **bold** text."}'
```

### Check grammar
```bash
curl -X POST "http://localhost:5040/notes/grammar?markdown=This+is+a+test+with+mistake." \
  -H "Content-Type: application/json"
```

### List all notes
```bash
curl http://localhost:5040/notes
```

### Get HTML rendering
```bash
curl http://localhost:5040/notes/<note_id>
```

### Get raw markdown
```bash
curl http://localhost:5040/notes/<note_id>/raw
```

### Delete a note
```bash
curl -X DELETE http://localhost:5040/notes/<note_id>
```

## Scan the API

<div align="center">

![Swagger](https://img.shields.io/badge/Swagger-Interactive%20Docs-blue?logo=swagger)
![FastAPI](https://img.shields.io/badge/FastAPI-Python-green?logo=fastapi)
![License](https://img.shields.io/badge/license-MIT-yellow.svg)

</div>

## Notes

- Notes are stored in the `notes/` directory as `.md` files.
- An index file `.index.json` tracks all saved notes.
- Grammar checking uses the free public LanguageTool API (`en-US`).
- Grammar and markdown rendering can also accept `.md` file uploads with `multipart/form-data`.
