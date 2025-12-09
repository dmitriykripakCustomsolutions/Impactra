import os
from cerebras.cloud.sdk import Cerebras
from constants import PROJECT_MANAGER_SYSTEM_CONTENT, PROJECT_MANAGER_SYSTEM_CONTENT_SUBTASKS_SPLITTING, COPYWRITER_SYSTEM_CONTENT

def _call_cerebras_ai_chat(prompt: str, model: str = "llama-3.3-70b", max_tokens: int = 800) -> str:
    client = Cerebras(api_key=os.environ.get("CEREBRAS_API_KEY"))

    response = client.chat.completions.create(
    model=model,
    messages=[
        {
                "role": "system", "content": PROJECT_MANAGER_SYSTEM_CONTENT_SUBTASKS_SPLITTING                
            },
            {
                "role": "user", "content": prompt
            } ]
    )

    print(response.choices[0].message.content)

    return response.choices[0].message.content


def _cerebras_ai_generate_folder_name(prompt: str, model: str = "llama-3.3-70b", max_tokens: int = 800) -> str:
    client = Cerebras(api_key=os.environ.get("CEREBRAS_API_KEY"))

    response = client.chat.completions.create(
    model=model,
    messages=[
        {
                "role": "system", "content": COPYWRITER_SYSTEM_CONTENT                
            },
            {
                "role": "user", "content": prompt
            } ]
    )

    print(response.choices[0].message.content)

    return response.choices[0].message.content