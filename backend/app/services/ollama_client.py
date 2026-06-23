# backend/app/services/ollama_client.py
import httpx
import json
import re
from app.config import settings

async def call_ollama(system_prompt: str, user_message: str) -> str:
    """
    Send a prompt to local Ollama and return the response text.
    Raises httpx.HTTPError on connection failure.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/chat",
            headers={"Content-Type": "application/json"},
            json={
                "model": settings.ollama_model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message}
                ],
                "options": {"temperature": 0.1, "num_predict": 500}
            }
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

def parse_llm_json(raw: str) -> dict:
    """
    Safely parse JSON from LLM output.
    Handles cases where the model wraps JSON in markdown code blocks.
    """
    # Strip markdown code fences if present: ```json ... ```
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    return json.loads(cleaned)