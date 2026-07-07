import asyncio
import json
import logging
import re

from openai import AsyncOpenAI

import google.generativeai as genai

from src.zone2.config import (
    OPENROUTER_BASE, OPENROUTER_API_KEY,
    GEMINI_API_KEY, GEMINI_MODEL,
    log,
)


_client_or = None
_genai_configured = False


def get_openrouter_client():
    global _client_or
    if _client_or is None:
        _client_or = AsyncOpenAI(base_url=OPENROUTER_BASE, api_key=OPENROUTER_API_KEY)
    return _client_or


def _ensure_genai():
    global _genai_configured
    if not _genai_configured and GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        _genai_configured = True


def _short_err(err):
    if hasattr(err, "message"):
        return err.message[:120]
    return str(err)[:120]


# ── Gemini backend ─────────────────────────────────────────────────────

GEMINI_SAFE = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]


async def gemini_llm_call(system_prompt, user_prompt, max_tokens=1000, retries=3):
    _ensure_genai()
    if not _genai_configured:
        log.error("Gemini not configured — set GEMINI_API_KEY in .env")
        return None

    model = genai.GenerativeModel(
        GEMINI_MODEL,
        system_instruction=system_prompt,
        safety_settings=GEMINI_SAFE,
    )

    for attempt in range(retries):
        try:
            resp = await model.generate_content_async(
                user_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0,
                    max_output_tokens=max_tokens,
                ),
            )
            text = resp.text
            if text:
                return text.strip()
            # Check if blocked by safety
            try:
                block_reason = resp.prompt_feedback.block_reason
                log.warning("  Gemini blocked: %s", block_reason)
            except Exception:
                pass
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


# ── Unified entry point ────────────────────────────────────────────────

async def llm_call(model, system_prompt, user_prompt, max_tokens=1000, retries=3):
    if model == "gemini":
        return await gemini_llm_call(system_prompt, user_prompt, max_tokens, retries)
    return await openrouter_llm_call(model, system_prompt, user_prompt, max_tokens, retries)


def parse_json_response(text):
    """Strip markdown fences and parse JSON from LLM response."""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, AttributeError) as e:
        log.warning("  JSON parse failed: %s", e)
        return None
