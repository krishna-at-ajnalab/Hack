from django.urls import path
from .views import hello_world, check_license_status, apply_ppan, get_captcha

urlpatterns = [
    path('hello/', hello_world, name='hello_world'),
    path('check-license-status/', check_license_status, name='check_license_status'),
    path('apply-ppan/', apply_ppan, name='apply_ppan'),
    path('get-captcha/', get_captcha, name='get_captcha'),
]
