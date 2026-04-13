from django.urls import path
from .views import UserByPhoneView, RegisterByPhoneView

urlpatterns = [
    path('login/', UserByPhoneView.as_view(), name='auth-login'),
    path('register/', RegisterByPhoneView.as_view(), name='auth-register'),
]
