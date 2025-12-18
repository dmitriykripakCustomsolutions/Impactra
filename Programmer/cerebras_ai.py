import os
import logging
from cerebras.cloud.sdk import Cerebras
from constants import SYSTEM_CONTENT, SYSTEM_CONTENT_FUNCTION_PER_CODE_CHUNK

logger = logging.getLogger(__name__)

def _call_cerebras_ai_chat(prompt: str, model: str = "llama-3.3-70b", max_tokens: int = 800) -> str:
    api_key = os.environ.get("CEREBRAS_API_KEY")
    
    if not api_key:
        error_msg = "CEREBRAS_API_KEY environment variable is not set"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.debug(f"Initializing Cerebras client with API key (first 20 chars): {api_key[:20]}...")
    
    client = Cerebras(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system", "content": SYSTEM_CONTENT_FUNCTION_PER_CODE_CHUNK                
            },
            {
                "role": "user", "content": prompt
            }
        ]
    )

    logger.debug(f"Cerebras API response received successfully")
    print(response.choices[0].message.content)

    return response.choices[0].message.content