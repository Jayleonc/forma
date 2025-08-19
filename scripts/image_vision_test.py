import os
import base64
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import mimetypes


"""
Simple vision test script.

- Hardcoded test image path and prompt.
- Supports OpenAI-compatible API via env overrides:
  - FORMA_OPENAI_BASE_URL (default: https://api.openai.com/v1)
  - FORMA_OPENAI_API_KEY  (no default; required unless you set DEFAULT_API_KEY below)
  - FORMA_OPENAI_MODEL    (default: gpt-4o-mini)

You can also change the constants below directly.
"""

# ======== Configuration (edit as you like) ========
DEFAULT_IMAGE_PATH = os.path.join("data", "image", "2.png")
DEFAULT_PROMPT = "请详细描述这张图片的内容，包括文字、图表与关键信息，不需要描述样式等无关内容。"
# Qwen2.5-VL-32B-Instruct
DEFAULT_MODEL = os.environ.get("FORMA_OPENAI_MODEL", "Qwen2.5-VL-32B-Instruct")
DEFAULT_BASE_URL = os.environ.get(
    "FORMA_OPENAI_BASE_URL", "https://ai.gitee.com/v1")
# Leave blank to force reading from env FORMA_OPENAI_API_KEY
DEFAULT_API_KEY: Optional[str] = os.environ.get(
    "FORMA_OPENAI_API_KEY", "")
# ==================================================


def encode_image_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def guess_mime_type(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    # Fallback to png if unknown
    return mime or "image/png"


def build_client(model: str, base_url: str, api_key: str) -> ChatOpenAI:
    # ChatOpenAI supports custom base_url and api_key for OpenAI-compatible providers
    return ChatOpenAI(model=model, base_url=base_url, api_key=api_key)


def run_vision(prompt: str, image_path: str, model: str, base_url: str, api_key: str) -> str:
    b64 = encode_image_to_base64(image_path)
    llm = build_client(model, base_url, api_key)
    mime = guess_mime_type(image_path)

    msg = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {
                "url": f"data:{mime};base64,{b64}"}},
        ]
    )

    result = llm.invoke([msg])
    # result is an AIMessage; .content is a string for text output
    return getattr(result, "content", "") or ""


def main() -> None:
    image_path = DEFAULT_IMAGE_PATH
    prompt = DEFAULT_PROMPT
    model = DEFAULT_MODEL
    base_url = DEFAULT_BASE_URL
    api_key = DEFAULT_API_KEY or os.environ.get("FORMA_OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "Missing API key. Set FORMA_OPENAI_API_KEY env var or edit DEFAULT_API_KEY in the script."
        )

    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    print("== Forma Vision Test ==")
    print(f"Image: {image_path}")
    print(f"Model: {model}")
    print(f"Base URL: {base_url}")

    try:
        content = run_vision(prompt, image_path, model, base_url, api_key)
        print("\n--- Result ---\n")
        print(content)
    except Exception as e:
        print("\nError:", repr(e))
        raise


if __name__ == "__main__":
    main()
