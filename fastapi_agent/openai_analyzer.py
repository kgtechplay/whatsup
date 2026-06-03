import os
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

load_dotenv()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class OpenAIAnalyzerError(RuntimeError):
    pass


def load_prompt(prompt_filename: str) -> str:
    prompt_path = PROMPTS_DIR / prompt_filename
    if not prompt_path.exists():
        raise OpenAIAnalyzerError(f"Prompt file not found: {prompt_path}")

    prompt_text = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt_text:
        raise OpenAIAnalyzerError(f"Prompt file is empty: {prompt_path}")

    return prompt_text


def extract_output_text(payload: Dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output = payload.get("output")
    if isinstance(output, list):
        text_chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                text_value = part.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    text_chunks.append(text_value.strip())
        if text_chunks:
            return "\n".join(text_chunks)

    raise OpenAIAnalyzerError("OpenAI response did not include output text.")


def generate_conversation_summary(
    all_messages: Optional[str], prompt_filename: str = "create_summary.md"
) -> str:
    if not OPENAI_API_KEY:
        raise OpenAIAnalyzerError("OPENAI_API_KEY is not configured.")

    conversation_text = (all_messages or "").strip()
    if not conversation_text:
        raise OpenAIAnalyzerError("No conversation text is available to summarize.")

    instructions = load_prompt(prompt_filename)
    response = requests.post(
        f"{OPENAI_API_BASE.rstrip('/')}/responses",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "input": [
                {"role": "developer", "content": instructions},
                {
                    "role": "user",
                    "content": (
                        "Conversation transcript to summarize:\n\n"
                        f"{conversation_text}"
                    ),
                },
            ],
        },
        timeout=90,
    )

    if response.status_code >= 400:
        raise OpenAIAnalyzerError(
            f"OpenAI API request failed ({response.status_code}): {response.text}"
        )

    return extract_output_text(response.json())
