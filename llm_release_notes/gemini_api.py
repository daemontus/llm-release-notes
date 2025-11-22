import os
import logging
import time
from typing import List

from google import genai

from .exceptions import GeminiAPIError


def get_gemini_client():
    """Get the Gemini client configured from environment variable GEMINI_API_KEY."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiAPIError("GEMINI_API_KEY is required for Gemini API")
    # The client automatically gets the API key from the environment variable GEMINI_API_KEY
    # when no arguments are passed
    return genai.Client()


def generate_text_from_context(prompt: str, files: List[str], model: str = "gemini-2.5-flash") -> str:
    """Generate text using Gemini by concatenating the prompt and context files."""
    client = get_gemini_client()
    total_tokens = 0

    # We create a list of file contents to pass to count_tokens.
    # The API is smart enough to handle a list of contents.
    file_contents = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                file_contents.append(f.read())
        except Exception as e:
            logging.getLogger(__name__).error("Warning: Could not read file %s, skipping. Error: %s", path, e)
            continue

    try:
        # Count tokens for file contents
        file_tokens_response = client.models.count_tokens(
            model=model,
            contents=file_contents
        )
        prompt_tokens_response = client.models.count_tokens(
            model=model,
            contents=prompt
        )
        total_tokens = file_tokens_response.total_tokens + prompt_tokens_response.total_tokens
    except Exception as e:
        raise GeminiAPIError(f"Failed to count tokens: {e}") from e

    logging.getLogger(__name__).info("Estimated token usage: %d", total_tokens)

    if total_tokens >= 2**20:
        raise GeminiAPIError("Data length exceeds available model context window.")

    uploaded_files = []
    logging.getLogger(__name__).info("Uploading files to Gemini API...")
    for path in files:
        try:
            logging.getLogger(__name__).info("  - Uploading %s...", os.path.basename(path))
            # Normally, the API automatically determines the mime type, but
            # here it has a problem with the .diff files, so we specify
            # everything as text explicitly
            file_ref = client.files.upload(file=path, config={ 'mime_type': "text/plain" })

            uploaded_files.append(file_ref)
            # Add a small delay to be kind to the upload API
            time.sleep(1)
        except Exception as e:
            logging.getLogger(__name__).error("    - Failed to upload %s: %s", os.path.basename(path), e)
            continue

    if not uploaded_files:
        logging.getLogger(__name__).info("No files were successfully uploaded. Aborting.")
        return ""

    try:
        logging.getLogger(__name__).info("All files uploaded. Sending prompt to Gemini model '%s'.", model)

        # The prompt now consists of the text instruction AND the list of file references
        # Build contents list with prompt and file references
        contents = [prompt] + uploaded_files
        resp = client.models.generate_content(
            model=model,
            contents=contents
        )

        try:
            logging.getLogger(__name__).info("Prompt done. Usage: %s", resp.usage_metadata)
            return resp.text
        except (ValueError, AttributeError):
            logging.getLogger(__name__).error("Warning: Response was blocked. Returning empty string.")
            if hasattr(resp, 'prompt_feedback'):
                logging.getLogger(__name__).error("Prompt Feedback: %s", resp.prompt_feedback)
            return ""
    except Exception as e:
        raise GeminiAPIError(f"Failed to generate text: {e}") from e
    finally:
        # Clean up the uploaded files to avoid incurring storage costs
        logging.getLogger(__name__).info("Cleaning up uploaded files...")
        for file_ref in uploaded_files:
            try:
                client.files.delete(name=file_ref.name)
                display_name = getattr(file_ref, 'display_name', file_ref.name)
                logging.getLogger(__name__).info("  - Deleted %s", file_ref.name)
            except Exception as e:
                display_name = getattr(file_ref, 'display_name', getattr(file_ref, 'name', 'unknown'))
                logging.getLogger(__name__).error("  - Failed to delete %s: %s", display_name, e)


