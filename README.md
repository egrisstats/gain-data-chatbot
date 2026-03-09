# GAIN Data Chatbot (Web)

This project creates a browser chatbot that answers questions using your GAIN datasets:
- `analysis_ready_main_roster.csv`
- `analysis_ready_group_roster.xlsx`

It works in two ways:
- Upload both files from the UI.
- Or use the default file paths from environment variables.

## 1) Setup

```powershell
cd "C:\Users\MITROVIF\OneDrive - UNHCR\Codex Tryout"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Then open `.env` and set:
- `OPENAI_API_KEY`
- (Optional) `MAIN_ROSTER_PATH` and `GROUP_ROSTER_PATH`

## 2) Run locally

```powershell
uvicorn main:app --reload --port 8000
```

Open:
- http://127.0.0.1:8000

## 3) Use the chatbot

1. Click `Load Default Paths`, or upload the two files.
2. Ask questions like:
   - `How many respondents by country?`
   - `What is the gender breakdown for each location?`
   - `Show average household size by displacement status.`

The app:
- Converts question to SQL against `main_roster` and `group_roster`.
- Runs SQL in DuckDB.
- Returns a plain-language answer grounded in the query results.

## 4) Put it online

Recommended: deploy on Render/Railway/Fly with this same app.

### Minimum deploy settings
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Environment variable: `OPENAI_API_KEY`
- Optional: do not set local file paths in cloud. Upload files through UI each session.

## Notes

- Only read-only SQL (`SELECT` / `WITH`) is allowed.
- If a question is ambiguous, the model makes a reasonable assumption.
