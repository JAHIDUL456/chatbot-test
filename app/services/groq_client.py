from typing import List, Dict, Optional, Tuple, Any, AsyncGenerator
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
        max_tokens: Optional[int] = None
    ) -> Tuple[str, Optional[Dict[str, int]]]:
        """
        Asynchronously sends a message history payload to Groq model to generate a completion response.
        
        :param messages: List of dictionaries matching Groq's ChatCompletion schema (role/content).
        :param temperature: Creativity parameter (0.0 to 2.0).
        :param max_tokens: Upper token limit for model output.
        :return: A tuple containing (generated response text, token usage dict).
        """
        try:
            logger.debug(
                f"Calling Groq API. Model: '{self.model}', Messages count: {len(messages)}"
            )
            
            completion = await self.client.chat.completions.create(
                messages=messages,  # type: ignore
                model=self.model,
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

    async def generate_chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronously streams the chat completion from Groq API token-by-token.
        Useful for providing immediate feedback on long responses and managing connection lifecycle.
        
        :param messages: List of dictionaries representing the chat history.
        :param temperature: Creativity parameter (0.0 to 2.0).
        :param max_tokens: Upper token limit for model output.
        :return: Async generator yielding text chunks as they arrive.
        """
        try:
            logger.debug(
                f"Calling Groq Streaming API. Model: '{self.model}', Messages count: {len(messages)}"
            )
            
            stream = await self.client.chat.completions.create(
                messages=messages,  # type: ignore
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content is not None:
                    yield content
                    
        except Exception as e:
            logger.error(f"Error in Groq streaming request flow: {str(e)}")
            raise e


# Singleton instance of GroqService to reuse connections efficiently across the app
groq_service = GroqService()
