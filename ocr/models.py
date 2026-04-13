from django.db import models

class CitizenshipDocument(models.Model):
    """
    Model to store citizenship document images and extracted data
    """
    image = models.ImageField(upload_to='citizenship_documents/')
    
    # Extracted data
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
    
    # Raw OCR data
    raw_text = models.TextField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Citizenship Document - {self.citizenship_no or 'Unknown'}"
