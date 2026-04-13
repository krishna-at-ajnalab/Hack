from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import JSONParser
from django.contrib.auth import get_user_model
from .serializers import UserSerializer

User = get_user_model()


class RegisterByPhoneView(APIView):
    parser_classes = [JSONParser]
    
    def post(self, request):
        try:
            phone = request.data.get("phone") if isinstance(request.data, dict) else None
            name = request.data.get("name", "") if isinstance(request.data, dict) else ""
        except (AttributeError, TypeError):
            return Response(
                {"error": "Invalid request data. Expected JSON format: {\"phone\": \"...\", \"name\": \"...\"}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        if not phone:
            return Response({"error": "Phone number is required."}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(phone=phone).exists():
            return Response({"error": "User with this phone already exists."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.create_user(phone=phone, name=name)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"message": "User created successfully", "user": UserSerializer(user).data}, status=status.HTTP_201_CREATED)


class UserByPhoneView(APIView):
    parser_classes = [JSONParser]
    
    def post(self, request):
        try:
            phone = request.data.get("phone") if isinstance(request.data, dict) else None
            name = request.data.get("name", "") if isinstance(request.data, dict) else ""
        except (AttributeError, TypeError):
            return Response(
                {"error": "Invalid request data. Expected JSON format: {\"phone\": \"<phone_number>\"}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not phone:
            return Response({"error": "Phone number is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Get or create user - creates if doesn't exist
        user, created = User.objects.get_or_create(
            phone=phone,
            defaults={'name': name}
        )
        
        action = "registered" if created else "logged in"
        serializer = UserSerializer(user)
        return Response(
            {
                "success": True,
                "action": action,
                "user": serializer.data
            }, 
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
