import logging
import os
import json
import re
from flask import Flask, request, jsonify
from cerebras.cloud.sdk import Cerebras
from constants import SYSTEM_CONTENT

app = Flask(__name__)

# Optional dependency: openai. We'll only use it if OPENAI_API_KEY is set.
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
            {"role": "system", "content": "You are an assistant that converts raw technical task descriptions into a JSON array of clear, small, implementation-ready subtasks for automated agents."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return resp.choices[0].message.content


def _call_cerebras_ai_chat(prompt: str, model: str = "llama-3.3-70b", max_tokens: int = 800) -> str:
    client = Cerebras(
    # This is the default and can be omitted
    api_key=os.environ.get("CEREBRAS_API_KEY")
    )

    # stream = client.chat.completions.create(
    #     messages=[
    #         {
    #             "role": "system", "content": "You are an assistant that converts raw technical task descriptions into a JSON array of clear, small, implementation-ready subtasks for automated agents."
    #         },
    #         {
    #             "role": "user", "content": prompt
    #         } 
            
    #     ],
    #     model=model,
    #     stream=True,
    #     max_completion_tokens=2048,
    #     temperature=0.2,
    #     top_p=1
    # )

    # for chunk in stream:
    #     print(chunk.choices[0].delta.content or "", end="")

    response = client.chat.completions.create(
    model=model,
    messages=[
        {
                "role": "system", "content": SYSTEM_CONTENT                
            },
            {
                "role": "user", "content": prompt
            } ]
    )

    print(response.choices[0].message.content)

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


@app.route('/receive-message', methods=['POST'])
def receive_message():
    """Receive raw technical task description and return structured subtasks JSON.

    Accepts JSON body with key 'message' (string) or form field 'message'.
    Response: { original: ..., tasks: [...], meta: {...} }
    """
    if request.is_json:
        data = request.get_json()
        raw = data.get('message') or data.get('text') or ''
    else:
        raw = request.form.get('message') or request.form.get('text') or ''

    if not raw:
        return jsonify({"error": "No 'message' provided"}), 400

    try:
        result = analyze_and_split_to_tasks(raw)
        return jsonify({"original": raw, "tasks": result['tasks'], "meta": result['meta']}), 200
    except Exception as e:
        app.logger.exception("Failed to analyze message")
        return jsonify({"error": "internal_error", "details": str(e)}), 500


@app.route('/receive-task-completion-result', methods=['POST'])
def receive_task_completion_result():
    # TODO: hook for receiving results from downstream agents; kept minimal to not break current behavior
    if request.is_json:
        data = request.get_json()
        return jsonify({"status": "received", "data": data}), 200
    else:
        return jsonify({"status": "ok", "message": "No JSON payload provided"}), 200


if __name__ == '__main__':
    # Enable basic logging
    logging.basicConfig(level=logging.INFO)
    # _call_openai_chat(prompt="Hello, world!")
    _call_cerebras_ai_chat(prompt="Write a simple array insertion sort algorithm in python.")
    app.run(host='0.0.0.0', port=5000)
