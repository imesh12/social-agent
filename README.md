# social-media-ai

Local-first AI social media automation foundation.

Current implementation:

- Manager Agent
- Trend Agent
- Research Agent
- Script Agent
- Voice Agent
- Video Agent
- Subtitle Agent
- SEO Agent
- Thumbnail Agent
- Publisher Agent
- APScheduler daily job manager
- Ollama-backed LLM service for research, scripts, and SEO
- Topic and script persistence
- Audio persistence
- Video persistence
- Subtitle persistence
- SEO metadata persistence
- Thumbnail persistence
- YouTube publish job persistence
- Scheduled job persistence
- Health, topic generation, script generation, audio generation, video generation, subtitle generation, and YouTube publishing APIs

TikTok, Instagram, thumbnails, and analytics are intentionally out of scope.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

## Run

```bash
uvicorn backend.main:app --reload
```

For local LLM generation, run Ollama and pull the default model:

```bash
ollama pull qwen3:8b
```

Default LLM settings are configured in `.env.example`:

- `LLM_PROVIDER=ollama`
- `OLLAMA_MODEL=qwen3:8b`
- `OLLAMA_BASE_URL=http://localhost:11434`

API:

- `GET /health`
- `POST /generate-topic`
- `POST /generate-script`
- `POST /generate-audio`
- `POST /generate-video`
- `POST /generate-subtitles`
- `POST /generate-seo`
- `POST /generate-thumbnail`
- `POST /publish-youtube`
- `POST /run-full-pipeline`
- `POST /run-daily-jobs`
- `GET /scheduler-status`

## Test

```bash
pytest
```

## Architecture

The project uses a modular FastAPI backend with SQLAlchemy repositories, Pydantic schemas, mock service integrations, and a Phase 1 multi-agent workflow. SQLite is the default database through `DATABASE_URL`, and the SQLAlchemy setup can move to PostgreSQL by changing the connection string and installing the appropriate driver.
