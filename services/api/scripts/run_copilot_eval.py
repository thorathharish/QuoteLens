"""Run the copilot evaluation set against the real LLM: Gemini on Vertex AI (GCP_PROJECT) or
OpenRouter (LLM_PROVIDER=openrouter + OPENROUTER_API_KEY), with LLM_ENABLED=true.

    uv run python scripts/run_copilot_eval.py            # hero BOM, prints a pass/fail table

Uses in-memory storage and the seed catalog; only the LLM calls are real.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.container import build_container
from app.infra.jobbus import InlineJobBus
from app.infra.repositories.memory import InMemoryDocumentStore
from app.main_api import create_app

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT.parents[1] / "data" / "samples" / "motor_controller.xlsx"


async def main() -> int:
    settings = get_settings()
    container = build_container(settings, store=InMemoryDocumentStore())
    if container.copilot.model is None:
        print(
            "LLM not configured: set LLM_PROVIDER=openrouter + OPENROUTER_API_KEY (or GCP_PROJECT)"
        )
        return 2
    cases: list[dict[str, Any]] = yaml.safe_load(
        (ROOT / "tests/evals/copilot_questions.yaml").read_text()
    )
    async with AsyncClient(
        transport=ASGITransport(app=create_app(container)), base_url="http://e"
    ) as c:
        pid = (
            await c.post("/api/v1/projects", json={"name": "Eval", "build_quantities": [100, 1000]})
        ).json()["id"]
        up = (
            await c.post(
                f"/api/v1/projects/{pid}/bom", files={"file": (SAMPLE.name, SAMPLE.read_bytes())}
            )
        ).json()
        await c.put(
            f"/api/v1/projects/{pid}/bom/mapping",
            json={"upload_id": up["upload_id"], "mapping": []},
        )
        assert isinstance(container.job_bus, InlineJobBus)
        await container.job_bus.drain()
        passed = 0
        for case in cases:
            sid = (await c.post(f"/api/v1/projects/{pid}/chat/sessions")).json()["id"]
            text = (
                await c.post(
                    f"/api/v1/projects/{pid}/chat/sessions/{sid}/messages",
                    json={"content": case["question"]},
                    timeout=120,
                )
            ).text
            events = [
                (b.split("\n", 1)[0][7:], json.loads(b.split("\n", 1)[1][6:]))
                for b in text.strip().split("\n\n")
            ]
            tools = {e["name"] for k, e in events if k == "tool_start"}
            answer = "".join(e["text"] for k, e in events if k == "token")
            done = dict(events).get("done", {})
            cites = len(dict(events).get("citations", {}).get("items", []))
            ok = (
                set(case["expect_tools"]) <= tools
                and done.get("grounded") is True
                and cites >= case["min_citations"]
                and case.get("expect_text", "") in answer
            )
            passed += ok
            print(
                f"{'PASS' if ok else 'FAIL'}  tools={sorted(tools)} cites={cites} "
                f"grounded={done.get('grounded')}  {case['question']}"
            )
        print(f"\n{passed}/{len(cases)} passed (target ≥ 8)")
        return 0 if passed >= 8 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
