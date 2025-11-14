import json
import re
import os
from constants import PROJECT_MANAGER_SYSTEM_CONTENT

try:
    import openai
except Exception:
    openai = None


def _call_openai_chat(prompt: str, model: str = "gpt-4o", max_tokens: int = 800) -> str:
    """Call OpenAI ChatCompletion and return assistant content.

    Requires environment variable OPENAI_API_KEY to be set and the openai package installed.
    If openai package or API key is missing, raises RuntimeError.
    """
    if openai is None:
        raise RuntimeError("openai package not available")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    openai.api_key = api_key
    resp = openai.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": PROJECT_MANAGER_SYSTEM_CONTENT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return resp.choices[0].message.content


def _heuristic_split(text: str):
    """Fallback splitter: splits text by sentences and groups them into small tasks.

    Returns list of task dicts.
    """
    # Split into sentences (simple) and filter empties
    sentences = [s.strip() for s in re.split(r'[\.\n\r]+', text) if s.strip()]
    tasks = []
    id_counter = 1
    # Group sentences to make tasks ~50 words max
    current = []
    current_words = 0
    for s in sentences:
        w = len(s.split())
        if current_words + w > 50 and current:
            title = current[0][:80]
            tasks.append({
                "id": id_counter,
                "title": title,
                "description": " ".join(current).strip(),
                "estimated_minutes": None,
                "tags": [],
            })
            id_counter += 1
            current = [s]
            current_words = w
        else:
            current.append(s)
            current_words += w
    if current:
        tasks.append({
            "id": id_counter,
            "title": current[0][:80],
            "description": " ".join(current).strip(),
            "estimated_minutes": None,
            "tags": [],
        })
    return tasks


def analyze_and_split_to_tasks(raw_text: str):
    """Analyze raw technical task text and return a structured list of subtasks.

    Preferred path: call OpenAI when available. Otherwise use a fallback heuristic.
    The function returns a dict with keys: tasks (list), meta (dict).
    """
    meta = {"ai_used": False, "model": None}
    # Prepare a robust instruction telling the model to output JSON
    prompt = (
        "Given the following raw technical task description, split it into a list of small, well-defined implementation tasks "
        "that are suitable to pass to another AI agent. For each task include: id (int), title (short string), description (detailed), "
        "estimated_minutes (optional number or null), tags (array of strings). Return ONLY valid JSON with the shape: {\"tasks\": [ {..}, ... ] }.\n\n"
        + f"Raw text:\n{raw_text}"
    )

    # Try to call OpenAI
    try:
        if openai is not None and os.environ.get("OPENAI_API_KEY"):
            meta["ai_used"] = True
            meta["model"] = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")
            raw_response = _call_openai_chat(prompt, model=meta["model"])  # may raise
            # Attempt to load JSON out of the assistant response
            # The assistant is instructed to return pure JSON; tolerate some surrounding text.
            j_text = raw_response.strip()
            # If code fences present, remove them
            j_text = re.sub(r"^```json\\n|```$", "", j_text, flags=re.I)
            # Try to find first JSON object in the text
            m = re.search(r"\{.*\}", j_text, flags=re.S)
            if m:
                j = json.loads(m.group(0))
                return {"tasks": j.get("tasks", []), "meta": meta}
            else:
                # fallback: try parse whole text
                j = json.loads(j_text)
                return {"tasks": j.get("tasks", []), "meta": meta}
    except Exception as e:
        app.logger.warning(f"OpenAI call failed or returned unparsable JSON: {e}")

    # Fallback heuristic
    tasks = _heuristic_split(raw_text)
    return {"tasks": tasks, "meta": meta}
