"""
Super Codex — Solo mode using OpenAI's best model (gpt-4o).

SUPER CODEX is the ChatGPT-SOLO conductor: a single, powerful AI using
OpenAI's flagship model as its intelligence engine.  It acts as the "lead"
brain that can also orchestrate the Council of 4.
"""

import os
from typing import Any, Dict, Iterator

from utils.logger import logger


# Default to gpt-4o; users may override via SUPER_CODEX_MODEL env var.
_DEFAULT_MODEL = "gpt-4o"

_SYSTEM_PROMPT = """\
You are Super Codex — the lead AI in the Super Conductor system, powered by \
OpenAI's best model. You are the primary intelligence in the Council of 4.

Your responsibilities:
1. Provide precise, expert-level answers with code where relevant.
2. When acting as Council Lead, synthesise input from other AI council \
members into one cohesive, superior response.
3. Always be direct, actionable, and technically accurate.
4. Cite which council members contributed when synthesising.

You are Solo mode when operating alone; you are Lead mode when the full \
Council of 4 is active.
"""


class SuperCodex:
    """
    ChatGPT-SOLO conductor — uses OpenAI's best model exclusively.

    Attributes:
        model:    The OpenAI model to use (default: gpt-4o).
        provider: Always "openai".
    """

    provider = "openai"

    def __init__(self, model: str | None = None):
        self.model = (
            model
            or os.getenv("SUPER_CODEX_MODEL", _DEFAULT_MODEL)
        )
        self.retriever = None  # optional; injected by server when memory is on
        self.current_skill = None
        self.skill_manager = None
        logger.info(
            f"SuperCodex initialised (provider=openai, model={self.model})"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self):
        """Return a fresh OpenAI client."""
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key or api_key.startswith("your_"):
            raise RuntimeError(
                "OPENAI_API_KEY is not configured. "
                "Set it in .env or as an environment variable."
            )
        return OpenAI(api_key=api_key)

    def _build_messages(self, query: str, context: str = "") -> list:
        system = _SYSTEM_PROMPT
        if self.current_skill and hasattr(self.current_skill, "prompt"):
            system = f"{self.current_skill.prompt}\n\n---\n\n{system}"

        user_content = query
        if context:
            user_content = (
                f"{query}\n\n"
                f"--- Relevant context from memory ---\n{context}"
            )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

    def _retrieve_context(self, query: str, platform_filter: str | None) -> tuple[str, list]:
        """Return (context_str, sources) from the retriever if available."""
        if self.retriever is None:
            return "", []
        try:
            results = self.retriever.search_conversations(
                query=query, n_results=5, platform_filter=platform_filter
            )
            parts = []
            sources = []
            for r in results:
                meta = r["metadata"]
                parts.append(
                    f"[{meta['platform'].upper()} — {meta['title']}]\n{r['content']}"
                )
                sources.append(
                    {
                        "platform": meta["platform"],
                        "title": meta["title"],
                        "score": r["score"],
                    }
                )
            return "\n\n---\n\n".join(parts), sources
        except Exception as exc:
            logger.warning(f"SuperCodex: retrieval error — {exc}")
            return "", []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def activate_skill(self, skill_name: str) -> bool:
        """Activate a skill (no-op if skill_manager is not set)."""
        if self.skill_manager:
            skill = self.skill_manager.get_skill(skill_name)
            if skill:
                self.current_skill = skill
                return True
        return False

    def chat(
        self,
        query: str,
        platform_filter: str | None = None,
    ) -> Dict[str, Any]:
        """
        Answer *query* using OpenAI's best model.

        Returns a dict with keys: response, sources, context_used, model.
        """
        context, sources = self._retrieve_context(query, platform_filter)
        messages = self._build_messages(query, context)
        client = self._get_client()

        try:
            resp = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=1500,
            )
            answer = resp.choices[0].message.content or ""
        except Exception as exc:
            logger.error(f"SuperCodex.chat error: {exc}")
            raise

        return {
            "response": answer,
            "sources": sources,
            "context_used": len(context),
            "model": f"openai:{self.model}",
        }

    def stream_chat(
        self,
        query: str,
        platform_filter: str | None = None,
    ) -> Iterator[Dict[str, Any]]:
        """Stream chat response chunks."""
        context, sources = self._retrieve_context(query, platform_filter)
        messages = self._build_messages(query, context)
        client = self._get_client()

        yield {"type": "sources", "data": sources}

        try:
            stream = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=1500,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield {"type": "content", "data": delta.content}
        except Exception as exc:
            logger.error(f"SuperCodex.stream_chat error: {exc}")
            yield {"type": "error", "data": str(exc)}
