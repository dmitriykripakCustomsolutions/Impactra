import os
from cerebras.cloud.sdk import Cerebras
from constants import SYSTEM_CONTENT

def _call_cerebras_ai_chat(prompt: str, model: str = "llama-3.3-70b", max_tokens: int = 800) -> str:
    client = Cerebras(api_key=os.environ.get("CEREBRAS_API_KEY"))

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

    return response.choices[0].message.content