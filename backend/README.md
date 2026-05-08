# BE-1 Search Pipeline

FastAPI backend for natural-language music search.

## Environment

Required for live API calls:

```env
LASTFM_API_KEY=
LASTFM_API_SECRET=
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3-flash-preview
```

iTunes and Deezer are used as public catalog sources for search metadata and album art.

## Run

```powershell
docker compose up -d --build
```

Health check:

```powershell
Invoke-RestMethod http://localhost:8001/health
```

Recommend:

```powershell
Invoke-RestMethod http://localhost:8001/recommend `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"query":"Younha Event Horizon"}'
```

## Shared imports for BE-2

```python
from app.services.catalog import CatalogClient
from app.services.lastfm import LastFmClient
from app.schemas.search import SelectedTrack, Tag
```
