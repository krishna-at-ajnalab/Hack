from rest_framework import serializers
from .models import CitizenshipDocument


class CitizenshipDocumentSerializer(serializers.ModelSerializer):
    """
    Serializer for CitizenshipDocument model
    """
    class Meta:
        model = CitizenshipDocument
        fields = [
            'id',
            'image',
            'citizenship_no',
            'name',
            'gender',
            'district',
            'birth_district',
            'municipality',
            'ward',
            'vdc_area',
            'dob',
            'full_address',
            'father',
            'mother',
            'office',
            'document_type',
            'raw_text',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'raw_text']


class CitizenshipDocumentUploadSerializer(serializers.ModelSerializer):
    """
    Serializer for uploading citizenship document images
    """
    class Meta:
        model = CitizenshipDocument
        fields = ['image']