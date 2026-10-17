"""Check the configured LLM (Vertex AI or OpenRouter) the way QuoteLens uses it: a plain
answer, structured column mapping and a tool call. Prints models and timings, never keys.

uv run python scripts/check_llm.py
"""

import asyncio
import sys
import time

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from app.config import LlmProvider, get_settings
from app.domain.enums import BomField
from app.infra.llm import ModelTier, build_chat_model
from app.ingestion.column_mapper import ColumnSample, GeminiHeaderMapper


@tool
def get_line_price(refdes: str) -> str:
    """Unit price in USD of the BOM line with this reference designator."""
    return f"{refdes}: 0.042 USD [E:ev_demo]"


async def _timed(label: str, coro: object) -> bool:
    start = time.perf_counter()
    try:
        result = await coro  # type: ignore[misc]
    except Exception as exc:  # report every failure, keep checking the rest
        print(f"FAIL  {label}: {type(exc).__name__}: {str(exc)[:300]}")
        return False
    print(f"OK    {label} ({time.perf_counter() - start:.1f} s): {result}")
    return True


async def main() -> int:
    settings = get_settings()
    flash = build_chat_model(settings, ModelTier.FLASH, max_output_tokens=512)
    pro = build_chat_model(settings, ModelTier.PRO, max_output_tokens=300)
    if flash is None or pro is None:
        print("No LLM configured. Local: LLM_PROVIDER=openrouter and OPENROUTER_API_KEY in .env")
        return 2
    if settings.llm_provider is LlmProvider.OPENROUTER:
        names = (settings.openrouter_flash_model, settings.openrouter_pro_model)
    else:
        names = (settings.gemini_flash_model, settings.gemini_pro_model)
    print(f"Provider {settings.llm_provider.value}: flash={names[0]}, pro={names[1]}\n")

    async def plain(model: object) -> str:
        reply = await model.ainvoke([HumanMessage(content="Reply with the single word: ready")])  # type: ignore[attr-defined]
        return repr(str(reply.content).strip()[:40])

    async def mapping() -> str:
        columns = [
            ColumnSample(0, "Mfr P/N", ["RC0603FR-0710KL", "GRM188R71H104KA93D"]),
            ColumnSample(1, "Qty / brd", ["4", "12"]),
            ColumnSample(2, "Desig.", ["R1-R4", "C1,C2"]),
            ColumnSample(3, "Line", ["1", "2"]),
        ]
        out = await GeminiHeaderMapper(flash).suggest(columns, list(BomField))
        return ", ".join(f"{s.column_index}->{s.field.value if s.field else None}" for s in out)

    async def tool_call() -> str:
        reply = await flash.bind_tools([get_line_price]).ainvoke(
            [HumanMessage(content="What does R7 cost? Use the tool.")]
        )
        calls = getattr(reply, "tool_calls", [])
        if not calls:
            raise RuntimeError(f"no tool call; replied {str(reply.content)[:120]!r}")
        return f"{calls[0]['name']}({calls[0]['args']})"

    checks = [
        await _timed("flash plain answer", plain(flash)),
        await _timed("pro plain answer (alternative explanations)", plain(pro)),
        await _timed(
            "column mapping, structured output (expect 0->mpn 1->qty_per 2->refdes)", mapping()
        ),
        await _timed("tool call (copilot)", tool_call()),
    ]
    print(f"\n{sum(checks)}/{len(checks)} checks passed")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
