# OpenAPI & Swagger Documentation

The backend API is now served using FastAPI. You can access the auto-generated OpenAPI and Swagger UI docs at:

- Swagger UI: [http://localhost:9001/docs](http://localhost:9001/docs) (default `python api_server.py`)
- OpenAPI JSON: [http://localhost:9001/openapi.json](http://localhost:9001/openapi.json)

Swagger UI's JS/CSS assets are served locally from the `swagger-ui-bundle` package (mounted at `/static/swagger-ui`) rather than pulled from a CDN, so the page renders correctly under the API's `default-src 'self'` Content-Security-Policy and works offline.

## How to Run the API Server

1. Install dependencies (if not already):
   ```bash
   pip install -r requirements.txt
   ```
2. Start the API server:
   ```bash
   python api_server.py
   ```
3. Visit [http://localhost:9001/docs](http://localhost:9001/docs) in your browser to view and interact with the API docs.

## Endpoints Implemented
- `GET /workflows` — List workflows
- `POST /workflows` — Create/import workflow
- `PUT /workflows/{id}` — Update workflow
- `DELETE /workflows/{id}` — Delete workflow
- `POST /workflows/export` — Export selected workflows
- `POST /workflows/backup` — Backup all workflows
- `POST /workflows/restore` — Restore workflows from backup
- `POST /workflows/pin` — Pin/unpin workflow
- `POST /workflows/favorite` — Add/remove favorite
- `POST /workflows/run` — Run workflow (local or NIM VM)

All endpoints and models are documented interactively in the Swagger UI.
