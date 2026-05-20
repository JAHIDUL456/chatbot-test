from typing import List, Dict, Optional, Tuple, Any
from groq import AsyncGroq
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class GroqService:
    """
    Service wrapper for the Groq Async Client.
    Provides methods to communicate with the Groq inference engine.
    """
    def __init__(self) -> None:
        # Initialize Groq client with the API Key and built-in exponential backoff retries (up to 5)
        # to automatically handle 429 Rate Limit responses transparently.
        self.client = AsyncGroq(api_key=settings.GROQ_API_KEY, max_retries=5)
        self.model = settings.GROQ_MODEL

    async def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None
    ) -> Tuple[str, Optional[Dict[str, int]]]:
        """
        Asynchronously sends a message history payload to Groq model to generate a completion response.
        
        :param messages: List of dictionaries matching Groq's ChatCompletion schema (role/content).
        :param temperature: Creativity parameter (0.0 to 2.0).
        :param max_tokens: Upper token limit for model output.
        :param model: The name of the model to use. Fallback to settings.GROQ_MODEL if None.
        :return: A tuple containing (generated response text, token usage dict).
        """
        try:
            target_model = model or self.model
            logger.debug(
                f"Calling Groq API. Model: '{target_model}', Messages count: {len(messages)}"
            )
            
            completion = await self.client.chat.completions.create(
                messages=messages,  # type: ignore
                model=target_model,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            result = completion.choices[0].message.content or ""
            
            # Extract usage metrics if returned by Groq API
            usage = None
            if completion.usage:
                usage = {
                    "prompt_tokens": completion.usage.prompt_tokens,
                    "completion_tokens": completion.usage.completion_tokens,
                    "total_tokens": completion.usage.total_tokens
                }
            
            logger.debug(f"Successfully fetched response from Groq. Token Usage: {usage}")
            return result, usage
            
        except Exception as e:
            logger.error(f"Error in Groq API request flow: {str(e)}")
            raise e


# Singleton instance of GroqService to reuse connections efficiently across the app
groq_service = GroqService()
