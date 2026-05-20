import json
import logging
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.groq_client import groq_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Default instruction optimized for detailed responses, eliminating token-wasting small talk
DEFAULT_SYSTEM_INSTRUCTION = (
    "You are a helpful, expert AI assistant. Your objective is to provide a complete, detailed, "
    "and highly informative answer to the user's query. Be direct, clear, and thorough. "
    "Do not omit necessary technical details, code blocks, or comprehensive explanations. "
    "Avoid unnecessary conversational filler, preambles, or greetings to minimize token usage "
    "and remain within rate limits, but provide a fully useful and complete answer."
)


@router.post(
    "/",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Chat Completion",
    description="Accepts chat conversation history, injects optimization prompts, and generates the next turn with usage metrics."
)
async def chat_completion(request: ChatRequest) -> ChatResponse:
    """
    Endpoint logic to interact with the LLM. Automatically injects token-saving instructions
    if no system message is present and tracks token counts in response.
    """
    try:
        # Check if user passed a custom system message
        has_system_msg = any(msg.role == "system" for msg in request.messages)
        
        formatted_messages = []
        if not has_system_msg:
            formatted_messages.append({"role": "system", "content": DEFAULT_SYSTEM_INSTRUCTION})
            
        for msg in request.messages:
            formatted_messages.append({"role": msg.role, "content": msg.content})
        
        response_text, usage_info = await groq_service.generate_chat_completion(
            messages=formatted_messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        
        return ChatResponse(
            response=response_text,
            model=settings.GROQ_MODEL,
            usage=usage_info  # type: ignore
        )
        
    except Exception as e:
        logger.error(f"Error in chat completion API endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate completion from the inference backend. Check server logs."
        )


@router.post(
    "/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream Chat Completion",
    description="Asynchronously streams the LLM response token-by-token using Server-Sent Events (SSE)."
)
async def chat_completion_stream(request: ChatRequest) -> StreamingResponse:
    """
    Streams the response back to the client token-by-token.
    This resolves timeouts for long answers and lets clients terminate the connection to save tokens.
    """
    try:
        has_system_msg = any(msg.role == "system" for msg in request.messages)
        
        formatted_messages = []
        if not has_system_msg:
            formatted_messages.append({"role": "system", "content": DEFAULT_SYSTEM_INSTRUCTION})
            
        for msg in request.messages:
            formatted_messages.append({"role": msg.role, "content": msg.content})

        async def event_generator():
            try:
                async for chunk in groq_service.generate_chat_stream(
                    messages=formatted_messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens
                ):
                    # Format as standard Server-Sent Event (SSE)
                    yield f"data: {json.dumps({'text': chunk})}\n\n"
                
                # Signal completion
                yield "data: [DONE]\n\n"
                
            except Exception as stream_err:
                logger.error(f"Error yielding stream chunks: {str(stream_err)}")
                yield f"data: {json.dumps({'error': 'An error occurred during streaming.'})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Prevent Nginx from buffering the response stream
            }
        )
        
    except Exception as e:
        logger.error(f"Error initializing chat stream: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize streaming response."
        )
