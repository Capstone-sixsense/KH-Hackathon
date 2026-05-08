# BE-1 Search Pipeline

FastAPI backend for natural-language music search.

## Environment

Required for live API calls:

```env
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
LASTFM_API_KEY=
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
```

## Run

```powershell
docker compose up -d --build
```

Health check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Search:

```powershell
Invoke-RestMethod http://localhost:8000/search `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"query":"아이유의 너랑나"}'
```

## Shared imports for BE-2

```python
from app.services.spotify import SpotifyClient
from app.services.lastfm import LastFmClient
from app.schemas.search import SelectedTrack, Tag
```
