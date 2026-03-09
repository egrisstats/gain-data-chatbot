import io
import json
import os
import re
from typing import Optional

import duckdb
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

DEFAULT_MAIN_PATH = os.getenv(
    "MAIN_ROSTER_PATH",
    r"C:/Users/MITROVIF/UNHCR/EGRISS Secretariat - Documents/905 - Implementation of Recommendations/01_GAIN Survey/Integration & GAIN Survey/EGRISS GAIN Survey 2025/10 Data/01 Analysis Ready Files/analysis_ready_main_roster.csv",
)
DEFAULT_GROUP_PATH = os.getenv(
    "GROUP_ROSTER_PATH",
    r"C:/Users/MITROVIF/UNHCR/EGRISS Secretariat - Documents/905 - Implementation of Recommendations/01_GAIN Survey/Integration & GAIN Survey/EGRISS GAIN Survey 2025/10 Data/01 Analysis Ready Files/analysis_ready_group_roster.xlsx",
)


class ChatRequest(BaseModel):
    message: str


app = FastAPI(title="GAIN Data Chatbot")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

db_conn: Optional[duckdb.DuckDBPyConnection] = None
schema_cache = ""


def _read_upload(upload: UploadFile, default_type: str) -> pd.DataFrame:
    content = upload.file.read()
    if not content:
        raise HTTPException(status_code=400, detail=f"{upload.filename} is empty.")
    buf = io.BytesIO(content)
    if upload.filename and upload.filename.lower().endswith(".csv"):
        return pd.read_csv(buf)
    if upload.filename and upload.filename.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(buf)
    if default_type == "csv":
        return pd.read_csv(buf)
    return pd.read_excel(buf)


def _table_schema(conn: duckdb.DuckDBPyConnection, table_name: str) -> str:
    rows = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    cols = [f"{r[1]} ({r[2]})" for r in rows]
    return f"{table_name}: " + ", ".join(cols)


def load_data(main_df: pd.DataFrame, group_df: pd.DataFrame) -> None:
    global db_conn, schema_cache
    conn = duckdb.connect(database=":memory:")
    conn.register("tmp_main", main_df)
    conn.register("tmp_group", group_df)
    conn.execute("CREATE OR REPLACE TABLE main_roster AS SELECT * FROM tmp_main")
    conn.execute("CREATE OR REPLACE TABLE group_roster AS SELECT * FROM tmp_group")

    main_schema = _table_schema(conn, "main_roster")
    group_schema = _table_schema(conn, "group_roster")
    schema_cache = f"{main_schema}\n{group_schema}"
    db_conn = conn


def try_default_load() -> Optional[str]:
    if not os.path.exists(DEFAULT_MAIN_PATH) or not os.path.exists(DEFAULT_GROUP_PATH):
        return "Default files not found. Please upload both files in the web interface."

    main_df = pd.read_csv(DEFAULT_MAIN_PATH)
    group_df = pd.read_excel(DEFAULT_GROUP_PATH)
    load_data(main_df, group_df)
    return None


def _extract_sql(raw: str) -> str:
    raw = raw.strip()
    try:
        as_json = json.loads(raw)
        if isinstance(as_json, dict) and "sql" in as_json:
            raw = as_json["sql"]
    except json.JSONDecodeError:
        pass

    code_block = re.findall(r"```(?:sql)?\s*(.*?)```", raw, flags=re.DOTALL | re.IGNORECASE)
    if code_block:
        raw = code_block[0].strip()

    raw = raw.strip().rstrip(";")
    return raw


def _validate_sql(sql: str) -> None:
    if not sql:
        raise HTTPException(status_code=400, detail="Model did not return SQL.")
    lowered = sql.lower()
    forbidden = ["insert ", "update ", "delete ", "drop ", "alter ", "create ", "truncate "]
    if any(token in lowered for token in forbidden):
        raise HTTPException(status_code=400, detail="Unsafe SQL detected and blocked.")
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise HTTPException(status_code=400, detail="Only SELECT/CTE queries are allowed.")


def _openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set.")
    return OpenAI(api_key=api_key)


def generate_sql(question: str) -> str:
    client = _openai_client()
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    prompt = (
        "You are a SQL analyst for DuckDB.\n"
        "Return ONLY a JSON object with keys: sql, note.\n"
        "Use only these tables and columns.\n"
        f"{schema_cache}\n"
        "Rules:\n"
        "- Use table names exactly: main_roster, group_roster.\n"
        "- Only produce SELECT or WITH queries.\n"
        "- Keep query concise and correct.\n"
        "- If a question is ambiguous, make a reasonable assumption and mention it in note.\n"
    )

    resp = client.responses.create(
        model=model,
        temperature=0,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": question},
        ],
    )
    sql = _extract_sql(resp.output_text)
    _validate_sql(sql)
    return sql


def answer_from_results(question: str, sql: str, df: pd.DataFrame) -> str:
    client = _openai_client()
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    preview = df.head(100).to_markdown(index=False) if not df.empty else "(no rows)"
    prompt = (
        "You are a data assistant for GAIN survey analysis.\n"
        "Answer only from the SQL results below.\n"
        "If rows are empty, clearly say no records matched.\n"
        "Be concise and include key numbers.\n"
    )
    user_msg = (
        f"Question: {question}\n\n"
        f"SQL used:\n{sql}\n\n"
        f"Rows returned: {len(df)}\n"
        f"Result preview:\n{preview}"
    )
    resp = client.responses.create(
        model=model,
        temperature=0.2,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_msg},
        ],
    )
    return resp.output_text.strip()


@app.on_event("startup")
def startup_load() -> None:
    try_default_load()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/load-data")
def load_data_endpoint(
    main_roster_file: Optional[UploadFile] = File(default=None),
    group_roster_file: Optional[UploadFile] = File(default=None),
):
    if main_roster_file is None and group_roster_file is None:
        message = try_default_load()
        if message:
            raise HTTPException(status_code=400, detail=message)
        return {"status": "ok", "message": "Loaded default data paths from environment."}

    if main_roster_file is None or group_roster_file is None:
        raise HTTPException(status_code=400, detail="Please upload both main and group roster files.")

    main_df = _read_upload(main_roster_file, "csv")
    group_df = _read_upload(group_roster_file, "xlsx")
    load_data(main_df, group_df)
    return {
        "status": "ok",
        "message": f"Data loaded. main_roster rows: {len(main_df)}, group_roster rows: {len(group_df)}",
    }


@app.post("/chat")
def chat(req: ChatRequest):
    if db_conn is None:
        raise HTTPException(status_code=400, detail="No data loaded. Upload files first.")
    question = req.message.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is empty.")

    sql = generate_sql(question)
    limited_sql = f"SELECT * FROM ({sql}) q LIMIT 1000"
    result_df = db_conn.execute(limited_sql).fetchdf()
    answer = answer_from_results(question, sql, result_df)
    return {
        "answer": answer,
        "sql": sql,
        "rows": len(result_df),
    }
