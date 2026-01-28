import requests
import json
import os

QWEN_API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
QWEN_MODEL = "kimi-k2-250905"
QWEN_API_KEY = "8c845a54-29f7-4b56-94a7-80c227d3d3f"

def call_qwen(system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
    headers = {"Content-Type": "application/json"}
    if QWEN_API_KEY:
        headers["Authorization"] = f"Bearer {QWEN_API_KEY}"

    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature
    }
    resp = requests.post(QWEN_API_URL, headers=headers, data=json.dumps(payload), timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]
