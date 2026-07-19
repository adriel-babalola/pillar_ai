import asyncio
import json
import logging
import re

from openai import AsyncOpenAI

from src.zone2.config import (
    OPENROUTER_BASE, OPENROUTER_API_KEY,
    GEMINI_API_KEY, GEMINI_MODEL,
    OLLAMA_API_KEY, OLLAMA_BASE,
    ALIBABA_API_KEY, ALIBABA_BASE,
    log,
)


_client_or = None
_genai_client = None


def get_openrouter_client():
    global _client_or
    if _client_or is None:
        import httpx
        http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))
        _client_or = AsyncOpenAI(base_url=OPENROUTER_BASE, api_key=OPENROUTER_API_KEY, http_client=http_client)
    return _client_or


def _get_genai_client():
    global _genai_client
    if _genai_client is None and GEMINI_API_KEY:
        from google import genai
        _genai_client = genai.Client(api_key=GEMINI_API_KEY)
    return _genai_client


def _short_err(err):
    if hasattr(err, "message"):
        return err.message[:120]
    return str(err)[:120]


# ── Gemini backend (google-genai SDK) ──────────────────────────────────

async def gemini_llm_call(system_prompt, user_prompt, max_tokens=1000, retries=3):
    client = _get_genai_client()
    if not client:
        log.error("Gemini not configured — set GEMINI_API_KEY in .env")
        return None

    from google.genai import types as genai_types

    for attempt in range(retries):
        try:
            resp = await client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0,
                    max_output_tokens=max_tokens,
                    safety_settings=[
                        genai_types.SafetySetting(category=cat, threshold="BLOCK_NONE")
                        for cat in [
                            "HARM_CATEGORY_HARASSMENT",
                            "HARM_CATEGORY_HATE_SPEECH",
                            "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                            "HARM_CATEGORY_DANGEROUS_CONTENT",
                        ]
                    ],
                ),
            )
            text = resp.text
            if text:
                return text.strip()
            block_reason = getattr(resp, "prompt_feedback", None)
            if block_reason:
                log.warning("  Gemini blocked: %s", block_reason)
            else:
                log.warning("  Gemini returned empty response")
            continue
        except Exception as e:
            err = str(e)[:120]
            log.warning("  Gemini attempt %d/%d: %s", attempt + 1, retries, err)
            if attempt < retries - 1:
                wait = (2 ** attempt) * 3
                await asyncio.sleep(wait)
    return None


# ── OpenRouter backend ─────────────────────────────────────────────────

async def openrouter_llm_call(model, system_prompt, user_prompt, max_tokens=1000, retries=3):
    client = get_openrouter_client()
    for attempt in range(retries):
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
            if content:
                return content.strip()
            log.warning("  LLM returned empty response")
            continue
        except Exception as e:
            err = _short_err(e)
            log.warning("  LLM call attempt %d/%d failed: %s", attempt + 1, retries, err)
            if "insufficient_quota" in err.lower() or "payment_required" in err.lower():
                log.error("  OpenRouter credits exhausted. Top up at https://openrouter.ai/")
                return None
            if attempt < retries - 1:
                wait = (2 ** attempt) * 3
                log.info("  Retrying in %ds...", wait)
                await asyncio.sleep(wait)
    return None


# ── Ollama Cloud backend (OpenAI-compatible) ────────────────────────────

async def ollama_llm_call(model, system_prompt, user_prompt, max_tokens=1000, retries=3):
    model_name = model.split(":", 1)[1]  # "ollama:glm-5.2" → "glm-5.2"
    if not OLLAMA_API_KEY:
        log.error("Ollama not configured — set OLLAMA_API_KEY in .env")
        return None

    import httpx
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))
    client = AsyncOpenAI(base_url=f"{OLLAMA_BASE}/v1", api_key=OLLAMA_API_KEY, http_client=http_client)
    for attempt in range(retries):
        try:
            resp = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
            if content:
                return content.strip()
            log.warning("  Ollama returned empty response")
            continue
        except Exception as e:
            err = _short_err(e)
            log.warning("  Ollama attempt %d/%d: %s", attempt + 1, retries, err)
            if attempt < retries - 1:
                wait = (2 ** attempt) * 3
                await asyncio.sleep(wait)
    return None


# ── Alibaba Cloud Model Studio backend (OpenAI-compatible) ─────────────

async def alibaba_llm_call(model, system_prompt, user_prompt, max_tokens=1000, retries=3):
    model_name = model.split(":", 1)[1]
    if not ALIBABA_API_KEY:
        log.error("Alibaba not configured — set ALIBABA_API_KEY in .env")
        return None

    import httpx
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))
    client = AsyncOpenAI(base_url=ALIBABA_BASE, api_key=ALIBABA_API_KEY, http_client=http_client)
    for attempt in range(retries):
        try:
            resp = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
            if content:
                return content.strip()
            log.warning("  Alibaba returned empty response")
            continue
        except Exception as e:
            err = _short_err(e)
            log.warning("  Alibaba attempt %d/%d: %s", attempt + 1, retries, err)
            if attempt < retries - 1:
                wait = (2 ** attempt) * 3
                await asyncio.sleep(wait)
    return None


# ── Unified entry point with comma-separated fallback ──────────────────

async def llm_call(model, system_prompt, user_prompt, max_tokens=1000, retries=3):
    models = [m.strip() for m in model.split(",")]
    for i, m in enumerate(models):
        if i > 0:
            log.info("  Fallback to model: %s", m)
        if m == "gemini":
            result = await gemini_llm_call(system_prompt, user_prompt, max_tokens, retries)
        elif m.startswith("alibaba:"):
            result = await alibaba_llm_call(m, system_prompt, user_prompt, max_tokens, retries)
        elif m.startswith("ollama:"):
            result = await ollama_llm_call(m, system_prompt, user_prompt, max_tokens, retries)
        else:
            result = await openrouter_llm_call(m, system_prompt, user_prompt, max_tokens, retries)
        if result:
            return result
    return None


def parse_json_response(text):
    """Strip markdown fences and parse JSON from LLM response."""
    raw = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, AttributeError) as e:
        log.warning("  JSON parse failed: %s — raw: %r", e, raw[:300])
        return None
