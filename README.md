# Emergency Dispatcher AI Assistant

This prototype is a real-time emergency dispatch co-pilot:

- plays demo emergency calls or accepts live input
- transcribes speech locally with `faster-whisper`
- extracts structured incident data
- suggests follow-up questions
- can speak translated dispatcher phrases with `edge-tts`

## Project structure

```text
assistant_prototype/
├── backend/   # FastAPI + Whisper + LLM routing + TTS
├── frontend/  # React + Vite UI
└── run.sh     # helper script to start both services
```

## Run On A New Computer

### 1. Install system requirements

Install these first:

- `git`
- Python `3.11+`
- Node.js `20+`
- `npm`

Optional:

- `ollama` if you want a fully local fallback LLM backend

Check versions:

```bash
python3 --version
node --version
npm --version
```

### 2. Clone the project

```bash
git clone <YOUR_REPO_URL>
cd assistant_prototype
```

### 3. Create the backend virtual environment

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

### 4. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 5. Create the backend environment file

Copy the example file:

```bash
cp backend/.env.example backend/.env
```

Minimum required to get a working LLM: paste your Claude key into `backend/.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
```

Defaults work for everything else. By default the app prefers Claude when `ANTHROPIC_API_KEY` is set, falls back to Ollama if running, then to rule-based extraction.

Other knobs in `.env.example` (only touch if you want to change defaults):

- `LLM_BACKEND=auto|claude|ollama|none` — force a backend
- `CLAUDE_MODEL`, `CLAUDE_TRANSLATE_MODEL` — model overrides
- `OLLAMA_HOST`, `OLLAMA_MODEL` — local LLM
- `WHISPER_MODEL`, `WHISPER_COMPUTE_TYPE`, `WHISPER_DEVICE`, `WHISPER_BEAM_SIZE` — STT tuning
- `LIVE_WHISPER_CHUNK_SEC` — live mic chunk size
- `STT_PROVIDER=whisper|reson8` — switch to Reson8 cloud STT (then set `RESON8_API_KEY`)

### 6. Demo audio

Demo MP3s are already committed in `backend/demo_audio/`. No action needed.

To regenerate (needs internet, uses `edge-tts`):

```bash
cd backend
source .venv/bin/activate
python generate_demos.py
cd ..
```

## LLM Backend Options

The backend auto-detects providers in this order:

1. `claude`
2. `ollama`
3. fallback mode with no live LLM

You can force one backend in `backend/.env`:

```env
LLM_BACKEND=claude
```

### Option A: Run fully local with Ollama

Install and start Ollama, then pull a model:

```bash
ollama serve
```

In another terminal:

```bash
ollama pull qwen2.5:7b-instruct
```

Then set this in `backend/.env`:

```env
LLM_BACKEND=ollama
OLLAMA_MODEL=qwen2.5:7b-instruct
```

### Option B: Run with Claude API

Put the API key in `backend/.env`:

```env
LLM_BACKEND=claude
ANTHROPIC_API_KEY=your_key_here
```

## Start The Prototype

You have two ways to run it.

### Option 1: Start everything with one script

From the project root:

```bash
bash run.sh
```

This script:

- checks `backend/.env`
- creates the Python virtual environment if missing
- installs backend dependencies if needed
- installs frontend dependencies if needed
- starts backend on port `8000`
- starts frontend on port `5173`

### Option 2: Start backend and frontend manually

Terminal 1:

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

Terminal 2:

```bash
cd frontend
npm run dev
```

Open:

```text
http://localhost:5173
```

## How To Use The Demo

1. Open the app in the browser.
2. Pick a scenario from the left panel.
3. The scenario audio plays and is transcribed.
4. The dispatch form fills automatically.
5. Suggestions and translated phrases appear when relevant.

## Useful Endpoints

Backend:

- `GET /` health check
- `GET /scenarios` list demo scenarios
- `GET /audio/{scenario_id}` get demo audio
- `GET /tts?text=...&language=...` synthesize speech
- `WS /ws` main live/demo websocket

## Troubleshooting

### `backend/.env not found`

Create it:

```bash
cp backend/.env.example backend/.env
```

### Frontend cannot connect

Make sure backend is running on `http://localhost:8000`.

### Whisper model downloads on first run

This is expected. Models are cached under `backend/models/`.

### Demo audio missing

Regenerate it:

```bash
cd backend
source .venv/bin/activate
python generate_demos.py
```

### Ollama not detected

Make sure both are true:

- `ollama serve` is running
- the model exists, for example `ollama pull qwen2.5:7b-instruct`

## Main Backend Dependencies

Backend uses:

- FastAPI
- Uvicorn
- `faster-whisper`
- `edge-tts`
- `anthropic`
- `openai`
- `python-dotenv`

Frontend uses:

- React
- TypeScript
- Vite
- Tailwind CSS
- Framer Motion
