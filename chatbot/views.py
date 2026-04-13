from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from openai import OpenAI
# Hardcoded API key for OpenRouter
OPENROUTER_API_KEY = "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"
OPENROUTER_MODEL = "openai/gpt-oss-20b:free"

class ChatbotAPIView(APIView):
    """
    API endpoint for chatbot requests with reasoning support.
    
    POST /chatbot/chat/
    
    Request body (single message):
    {
        "message": "How many r's are in the word 'strawberry'?",
        "enable_reasoning": true
    }
    
    Request body (multi-turn with reasoning):
    {
        "messages": [
            {"role": "user", "content": "How many r's are in 'strawberry'?"},
            {
                "role": "assistant",
                "content": "...",
                "reasoning_details": {...}
            },
            {"role": "user", "content": "Are you sure? Think carefully."}
        ],
        "enable_reasoning": true
    }
    
    Response:
    {
        "success": true,
        "message": "User message or conversation status",
        "response": "AI response",
        "reasoning_details": {...},
        "model": "openai/gpt-oss-20b:free",
        "enable_reasoning": true
    }
    """
    
    def post(self, request):
        """Handle chat request"""
        try:
            # Extract message from request
            message = request.data.get('message')
            messages = request.data.get('messages', [])
            enable_reasoning = request.data.get('enable_reasoning', True)
            
            if not message and not messages:
                return Response(
                    {
                        "success": False,
                        "error": "Message field or messages array is required"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Initialize OpenAI client with OpenRouter
            client = OpenAI(
                api_key=OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1"
            )
            
            # Build messages list
            if message and not messages:
                messages = [{"role": "user", "content": message}]
            elif message and messages:
                messages.append({"role": "user", "content": message})
            
            # Create chat completion with reasoning
            extra_body = {}
            if enable_reasoning:
                extra_body["reasoning"] = {"enabled": True}
            
            response = client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=messages,
                extra_body=extra_body if extra_body else None,
                stream=False
            )
            
            # Extract response
            response_message = response.choices[0].message
            ai_response = response_message.content
            reasoning_details = getattr(response_message, 'reasoning_details', None)
            
            return Response(
                {
                    "success": True,
                    "message": message if message else "Conversation continued",
                    "response": ai_response,
                    "reasoning_details": reasoning_details,
                    "model": OPENROUTER_MODEL,
                    "enable_reasoning": enable_reasoning
                },
                status=status.HTTP_200_OK
            )
        
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "error": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



