"""Gemini API wrapper for text generation from a set of context files."""

import os
import logging
import time

from typing import List


import google.generativeai as genai


def get_gemini_client() -> None:
    """Configure the Gemini SDK from environment variable GEMINI_API_KEY."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for Gemini API")
    genai.configure(api_key=api_key)


def generate_text_from_context(prompt: str, files: List[str], model: str = "gemini-2.5-flash") -> str:
    """Generate text using Gemini by concatenating the prompt and context files.
    """
    get_gemini_client()
    
    model_obj = genai.GenerativeModel(model)
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
            
    response = model_obj.count_tokens(file_contents)
    total_tokens = response.total_tokens + genai.GenerativeModel(model).count_tokens(prompt).total_tokens

    logging.getLogger(__name__).info("Estimated token usage: %d", total_tokens)

    if total_tokens >= 2**20:
        raise RuntimeError("Data length exceeds available model context window.")

    uploaded_files = []
    logging.getLogger(__name__).info("Uploading files to Gemini API...")
    for path in files:
        try:
            logging.getLogger(__name__).info("  - Uploading %s...", os.path.basename(path))
            # Normally, the API automatically determines the mime type, but
            # here it has a problem with the .diff files, so we specify 
            # everything as text explicitly
            file_ref = genai.upload_file(path=path, mime_type="text/plain") 
            
            uploaded_files.append(file_ref)
            # Add a small delay to be kind to the upload API
            time.sleep(1) 
        except Exception as e:
            logging.getLogger(__name__).error("    - Failed to upload %s: %s", os.path.basename(path), e)
            continue
    
    if not uploaded_files:
        logging.getLogger(__name__).info("No files were successfully uploaded. Aborting.")
        return ""

    logging.getLogger(__name__).info("All files uploaded. Sending prompt to Gemini model '%s'.", model)
    
    model_obj = genai.GenerativeModel(model)
    
    # The prompt now consists of the text instruction AND the list of file references
    resp = model_obj.generate_content([prompt] + uploaded_files)
    
    # Clean up the uploaded files to avoid incurring storage costs
    logging.getLogger(__name__).info("Cleaning up uploaded files...")
    for file_ref in uploaded_files:
        try:
            genai.delete_file(file_ref.name)
            logging.getLogger(__name__).info("  - Deleted %s", file_ref.display_name)
        except Exception as e:
            logging.getLogger(__name__).error("  - Failed to delete %s: %s", file_ref.display_name, e)

    try:
        logging.getLogger(__name__).info("Prompt done. Usage: %s", resp.usage_metadata)
        return resp.text
    except ValueError:
        logging.getLogger(__name__).error("Warning: Response was blocked. Returning empty string.")
        logging.getLogger(__name__).error("Prompt Feedback: %s", resp.prompt_feedback)
        return ""

