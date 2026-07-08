"""Gemini / Claude / OpenAI を単一インターフェースで呼び出すラッパー。"""

import httpx

from .config import settings

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)


async def _call_gemini(system_prompt: str, user_message: str) -> str:
    # google-generativeai（非推奨SDK）はAPIキーを渡してもADCを要求してくる既知の不具合が
    # あるため、SDKを使わずREST APIを直接呼び出す
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_message}]}],
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            GEMINI_URL,
            params={"key": settings.gemini_api_key},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def _call_claude(system_prompt: str, user_message: str) -> str:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


async def _call_openai(system_prompt: str, user_message: str) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content


_PROVIDERS = {
    "gemini": _call_gemini,
    "claude": _call_claude,
    "openai": _call_openai,
}


async def generate_reply(
    user_message: str, system_prompt: str, provider: str | None = None
) -> str:
    provider = provider or settings.default_model_provider
    handler = _PROVIDERS.get(provider)
    if handler is None:
        raise ValueError(f"unknown provider: {provider}")
    return await handler(system_prompt, user_message)
