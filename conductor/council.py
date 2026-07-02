"""
Council of 4 Super Conductor.

The Council consists of four AI providers:
  1. Codex / ChatGPT  (OpenAI)  — LEAD — synthesises all responses
  2. Gemini           (Google)
  3. Grok             (xAI)
  4. Claude           (Anthropic)

Each council member answers the query independently; the Lead (OpenAI /
Super Codex) then synthesises the answers into a single, authoritative
response.  Only providers with configured API keys participate; the system
gracefully degrades if fewer than 4 keys are available.
"""

import asyncio
import os
from typing import Any, Dict, Iterator, List

from utils.logger import logger
from conductor.super_codex import SuperCodex, _SYSTEM_PROMPT as _LEAD_SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# Council member definitions
# ---------------------------------------------------------------------------

_COUNCIL_MEMBERS = [
    # (name, provider_tag, env_var, model)
    ("Codex/ChatGPT", "openai",    "OPENAI_API_KEY",    "gpt-4o"),
    ("Gemini",        "google",    "GOOGLE_API_KEY",    "gemini-1.5-flash"),
    ("Grok",          "xai",       "XAI_API_KEY",       "grok-2-latest"),
    ("Claude",        "anthropic", "ANTHROPIC_API_KEY", "claude-3-5-haiku-latest"),
]

_MEMBER_SYSTEM_PROMPT = """\
You are a council member AI assistant. Provide a clear, concise, and expert \
answer to the user's question. Be honest about uncertainty. Your response \
will be reviewed and synthesised by the Council Lead (Super Codex / ChatGPT).
"""

_SYNTHESIS_PROMPT = """\
You are Super Codex, the Lead of the Council of 4. Below are the independent \
answers from your three council members ({members}). Your job is to:

1. Identify the strongest insights from each member.
2. Resolve any contradictions with the most accurate information.
3. Produce one authoritative, comprehensive final answer.
4. At the end, briefly note which council member(s) contributed each key point.

Council responses:
{council_responses}

Original question: {query}

Synthesise the above into your definitive answer now.
"""


# ---------------------------------------------------------------------------
# Individual member callers (sync, run inside executor)
# ---------------------------------------------------------------------------

def _call_openai(query: str, model: str) -> str:
    from openai import OpenAI
    key = os.getenv("OPENAI_API_KEY", "")
    if not key or key.startswith("your_"):
        raise RuntimeError("OPENAI_API_KEY not set")
    client = OpenAI(api_key=key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _MEMBER_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        temperature=0.7,
        max_tokens=800,
    )
    return resp.choices[0].message.content or ""


def _call_google(query: str, model: str) -> str:
    import google.generativeai as genai
    key = os.getenv("GOOGLE_API_KEY", "")
    if not key:
        raise RuntimeError("GOOGLE_API_KEY not set")
    genai.configure(api_key=key)
    m = genai.GenerativeModel(
        model, system_instruction=_MEMBER_SYSTEM_PROMPT
    )
    resp = m.generate_content(
        query,
        generation_config={"temperature": 0.7, "max_output_tokens": 800},
    )
    return resp.text or ""


def _call_xai(query: str, model: str) -> str:
    from openai import OpenAI
    key = os.getenv("XAI_API_KEY", "")
    if not key:
        raise RuntimeError("XAI_API_KEY not set")
    client = OpenAI(api_key=key, base_url="https://api.x.ai/v1")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _MEMBER_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        temperature=0.7,
        max_tokens=800,
    )
    return resp.choices[0].message.content or ""


def _call_anthropic(query: str, model: str) -> str:
    import anthropic
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.create(
        model=model,
        max_tokens=800,
        system=_MEMBER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": query}],
    )
    return "".join(
        block.text for block in resp.content if hasattr(block, "text")
    )


_CALLER_MAP = {
    "openai":    _call_openai,
    "google":    _call_google,
    "xai":       _call_xai,
    "anthropic": _call_anthropic,
}


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------

async def _gather_member_responses(
    query: str,
    members: List[tuple],
) -> List[Dict[str, Any]]:
    """
    Call each council member concurrently and return their responses.
    Members that fail (e.g. missing key) are reported as errors but do
    not block the others.
    """
    loop = asyncio.get_event_loop()

    async def _one(name, provider, _env, model):
        caller = _CALLER_MAP.get(provider)
        if caller is None:
            return {"name": name, "provider": provider, "text": None,
                    "error": f"No caller for provider '{provider}'"}
        try:
            text = await loop.run_in_executor(None, caller, query, model)
            logger.info(f"Council member '{name}' responded ({len(text)} chars)")
            return {"name": name, "provider": provider, "text": text, "error": None}
        except Exception as exc:
            logger.warning(f"Council member '{name}' failed: {exc}")
            return {"name": name, "provider": provider, "text": None,
                    "error": str(exc)}

    tasks = [_one(*m) for m in members]
    return await asyncio.gather(*tasks)


# ---------------------------------------------------------------------------
# CouncilConductor
# ---------------------------------------------------------------------------

class CouncilConductor:
    """
    Council of 4 Super Conductor.

    Queries up to 4 AI providers in parallel; Super Codex (OpenAI) acts as
    the Lead and synthesises all council responses into a final answer.

    If fewer than 4 providers are configured the council runs with only the
    available members.  If the OpenAI key is missing the synthesis step falls
    back to the best available provider.
    """

    def __init__(self):
        self.retriever = None  # injected externally when memory is on
        self.current_skill = None
        self.skill_manager = None
        self._lead = SuperCodex()  # always OpenAI

        # Determine which members are available (key present)
        self.members: List[tuple] = []
        for entry in _COUNCIL_MEMBERS:
            _name, _provider, env_var, _model = entry
            if os.getenv(env_var, ""):
                self.members.append(entry)

        names = [m[0] for m in self.members]
        logger.info(
            f"CouncilConductor initialised — "
            f"{len(self.members)}/4 members available: {names}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _available_member_names(self) -> List[str]:
        return [m[0] for m in self.members if m[1] != "openai"]

    def _synthesise(self, query: str, responses: List[Dict[str, Any]]) -> str:
        """
        Use the Lead (Super Codex) to synthesise council responses.
        Responses from failed members are excluded.
        """
        successful = [r for r in responses if r["text"]]
        if not successful:
            return (
                "All council members failed to respond. "
                "Please check your API keys."
            )

        # If only one member responded, return directly (no synthesis needed)
        if len(successful) == 1:
            return successful[0]["text"]

        parts = []
        member_names = []
        for r in successful:
            parts.append(f"### {r['name']} says:\n{r['text']}")
            member_names.append(r["name"])

        council_block = "\n\n".join(parts)
        synthesis_query = _SYNTHESIS_PROMPT.format(
            members=", ".join(member_names),
            council_responses=council_block,
            query=query,
        )

        try:
            result = self._lead.chat(synthesis_query)
            return result["response"]
        except Exception as exc:
            logger.error(f"CouncilConductor synthesis failed: {exc}")
            # Fallback: return the best single response
            return successful[0]["text"]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def activate_skill(self, skill_name: str) -> bool:
        return self._lead.activate_skill(skill_name)

    def chat(
        self,
        query: str,
        platform_filter: str | None = None,
    ) -> Dict[str, Any]:
        """
        Query all council members concurrently then synthesise.

        Returns a dict with:
          response       — final synthesised answer
          sources        — memory sources (if retriever set)
          council        — list of individual member responses
          members_used   — count of successful council members
          model          — always "council:openai-lead"
        """
        # Optionally retrieve memory context (prepend to query for all members)
        context = ""
        sources: list = []
        if self.retriever is not None:
            try:
                results = self.retriever.search_conversations(
                    query=query, n_results=5,
                    platform_filter=platform_filter,
                )
                parts = []
                for r in results:
                    meta = r["metadata"]
                    parts.append(
                        f"[{meta['platform'].upper()} — {meta['title']}]\n"
                        f"{r['content']}"
                    )
                    sources.append(
                        {"platform": meta["platform"],
                         "title": meta["title"],
                         "score": r["score"]}
                    )
                context = "\n\n---\n\n".join(parts)
            except Exception as exc:
                logger.warning(f"CouncilConductor retrieval error: {exc}")

        enriched_query = query
        if context:
            enriched_query = (
                f"{query}\n\n"
                f"--- Relevant memory context ---\n{context}"
            )

        # Gather member responses (async → sync bridge)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Inside an async context (e.g. FastAPI) — use asyncio.run
                # via a new thread to avoid nesting
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        _gather_member_responses(enriched_query, self.members),
                    )
                    responses = future.result()
            else:
                responses = loop.run_until_complete(
                    _gather_member_responses(enriched_query, self.members)
                )
        except Exception as exc:
            logger.error(f"CouncilConductor gather error: {exc}")
            responses = []

        final_answer = self._synthesise(query, responses)
        successful = [r for r in responses if r["text"]]

        return {
            "response": final_answer,
            "sources": sources,
            "context_used": len(context),
            "council": [
                {
                    "name": r["name"],
                    "provider": r["provider"],
                    "response": r["text"],
                    "error": r["error"],
                }
                for r in responses
            ],
            "members_used": len(successful),
            "model": "council:openai-lead",
        }

    def stream_chat(
        self,
        query: str,
        platform_filter: str | None = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        Streaming wrapper around chat().

        Yields source chunk, then council member chunks, then final answer.
        """
        result = self.chat(query, platform_filter=platform_filter)

        yield {"type": "sources", "data": result["sources"]}

        # Emit individual council responses first
        for member in result["council"]:
            if member["response"]:
                yield {
                    "type": "council_member",
                    "data": {
                        "name": member["name"],
                        "provider": member["provider"],
                        "response": member["response"],
                    },
                }

        # Stream final synthesised answer in chunks
        chunk_size = 120
        text = result["response"]
        for i in range(0, len(text), chunk_size):
            yield {"type": "content", "data": text[i: i + chunk_size]}
