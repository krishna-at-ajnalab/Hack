from django.db import models
from django.conf import settings


class CitizenshipDocument(models.Model):
    image = models.ImageField(upload_to='citizenship_documents/')
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name='citizenship_documents')
    citizenship_no = models.CharField(max_length=255, null=True, blank=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    gender = models.CharField(max_length=50, null=True, blank=True)
    district = models.CharField(max_length=255, null=True, blank=True)
    birth_district = models.CharField(max_length=255, null=True, blank=True)
    municipality = models.CharField(max_length=255, null=True, blank=True)
    ward = models.CharField(max_length=50, null=True, blank=True)
    vdc_area = models.CharField(max_length=255, null=True, blank=True)
    dob = models.CharField(max_length=50, null=True, blank=True)  # YYYY-MM-DD format
    full_address = models.TextField(null=True, blank=True)
    father = models.CharField(max_length=255, null=True, blank=True)
    mother = models.CharField(max_length=255, null=True, blank=True)
    office = models.CharField(max_length=255, null=True, blank=True)
    document_type = models.CharField(max_length=100, null=True, blank=True)
    raw_text = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Citizenship Document - {self.citizenship_no or 'Unknown'}"
