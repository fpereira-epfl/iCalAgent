#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from typing import Any

class GPTConnector:
    """Thin wrapper around OpenAI responses for JSON-first prompts."""

    def __init__(self, model: str = "gpt-4o-mini"):
        from dotenv import load_dotenv
        from openai import OpenAI

        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment or .env file")

        timeout_seconds = float(os.getenv("ICALAGENT_OPENAI_TIMEOUT_SECONDS", "120"))
        max_retries = int(os.getenv("ICALAGENT_OPENAI_MAX_RETRIES", "2"))

        self.client = OpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )
        self.model = model

    def send_prompt(
        self,
        prompt: str,
        system: str | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
            timeout=timeout_seconds,
        )

        message = response.choices[0].message.content
        if not message:
            return {"error": "No response from model"}

        try:
            return json.loads(message)
        except json.JSONDecodeError:
            return {"raw_response": message}
