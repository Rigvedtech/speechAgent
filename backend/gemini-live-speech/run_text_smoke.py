"""
Quick Live API check (TEXT modality) using GEMINI_LIVE_SMOKE_MODEL.

Use this before debugging audio to confirm your API key and model access.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from google import genai
from google.genai import types
from settings import load_settings


async def _run() -> None:
    settings = load_settings()
    client = genai.Client(api_key=settings.google_api_key)
    config = types.LiveConnectConfig(response_modalities=["TEXT"])

    print(f"Connecting with model={settings.smoke_model!r} ...", flush=True)
    async with client.aio.live.connect(model=settings.smoke_model, config=config) as session:
        await session.send_client_content(
            turns=types.Content(
                role="user",
                parts=[types.Part(text="Reply with one short English sentence only.")],
            ),
            turn_complete=True,
        )
        async for message in session.receive():
            sc = message.server_content
            if sc and sc.model_turn and sc.model_turn.parts:
                for part in sc.model_turn.parts:
                    if part.text:
                        print(part.text, end="", flush=True)
            if sc and sc.turn_complete:
                print(flush=True)
                break


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini Live text smoke test.")
    parser.add_argument(
        "--model",
        default="",
        help="Override GEMINI_LIVE_SMOKE_MODEL for this run.",
    )
    args = parser.parse_args()

    if args.model:
        os.environ["GEMINI_LIVE_SMOKE_MODEL"] = args.model

    try:
        asyncio.run(_run())
    except Exception as exc:  # pragma: no cover
        print(f"Failed: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
