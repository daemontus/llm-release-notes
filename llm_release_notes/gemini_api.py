import os
from typing import List

import google.generativeai as genai


def get_gemini_client() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for Gemini API")
    genai.configure(api_key=api_key)


def generate_text_from_context(prompt: str, files: List[str], model: str = "gemini-1.5-pro") -> str:
    get_gemini_client()
    # Concatenate files as a single long input. For true multi-part, use files API; kept simple here.
    contents: List[str] = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                contents.append(f"\n\n===== FILE: {os.path.basename(path)} =====\n" + f.read())
        except Exception:
            continue
    full_input = prompt + "\n\n" + "\n".join(contents)
    model_obj = genai.GenerativeModel(model)
    resp = model_obj.generate_content(full_input)
    return getattr(resp, "text", "") or ""


