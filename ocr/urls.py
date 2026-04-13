from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CitizenshipDocumentViewSet

router = DefaultRouter()
router.register(r'citizenship', CitizenshipDocumentViewSet, basename='citizenship')

urlpatterns = [
    path('', include(router.urls)),
]
