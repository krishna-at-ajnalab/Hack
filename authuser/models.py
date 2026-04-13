from django.db import models

import re
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.core.exceptions import ValidationError

def validate_phone_number(value):
    """Validate phone number: exactly 10 digits."""
    phone_regex = r'^[0-9]{10}$'
    if not re.match(phone_regex, value):
        raise ValidationError("Phone number must be 10 digits.")


class CustomUserManager(BaseUserManager):
    """Custom manager for User model with phone as username."""
    
    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError('Phone number is required.')
        
        user = self.model(phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(phone, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin,):

    phone = models.CharField(
        max_length=10,
        unique=True,
        validators=[validate_phone_number],
        help_text="Phone number must be 10 digits."
    )
    name = models.CharField(max_length=150, blank=True)
    
    objects = CustomUserManager()
    
    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = []
    
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
    
    def __str__(self):
        return f"User({self.phone})-{self.name}"
    