from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import render
from .models import CitizenshipDocument
from .serializers import CitizenshipDocumentSerializer, CitizenshipDocumentUploadSerializer
from .ocr_utils import process_citizenship_image
from django.core.files.base import ContentFile
import logging

logger = logging.getLogger(__name__)


class CitizenshipDocumentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for handling citizenship document uploads and OCR processing
    """
    queryset = CitizenshipDocument.objects.all()
    serializer_class = CitizenshipDocumentSerializer
    parser_classes = (MultiPartParser, FormParser)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CitizenshipDocumentUploadSerializer
        return CitizenshipDocumentSerializer
    
    def create(self, request, *args, **kwargs):
        """
        Handle image upload and OCR processing
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            # Get the uploaded image
            image_file = request.FILES.get('image')
            
            if not image_file:
                return Response(
                    {'error': 'No image provided'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Process the image and extract data
            extracted_data = process_citizenship_image(image_file)
            
            # Get user_id from request data (optional)
            user_id = request.data.get('user')
            
            # Save the document with extracted data
            document = CitizenshipDocument.objects.create(
                image=image_file,
                user_id=user_id,
                citizenship_no=extracted_data.get('citizenship_no'),
                name=extracted_data.get('name'),
                gender=extracted_data.get('gender'),
                district=extracted_data.get('district'),
                birth_district=extracted_data.get('birth_district'),
                municipality=extracted_data.get('municipality'),
                ward=extracted_data.get('ward'),
                vdc_area=extracted_data.get('vdc_area'),
                dob=extracted_data.get('dob'),
                full_address=extracted_data.get('full_address'),
                father=extracted_data.get('father'),
                mother=extracted_data.get('mother'),
                office=extracted_data.get('office'),
                document_type=extracted_data.get('document_type'),
                raw_text=extracted_data.get('raw_text'),
            )
            
            # Return the processed data
            response_serializer = CitizenshipDocumentSerializer(document)
            return Response(
                response_serializer.data,
                status=status.HTTP_201_CREATED
            )
        
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            return Response(
                {'error': f'Error processing image: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['post'], parser_classes=(MultiPartParser, FormParser))
    def process_image(self, request):
        """
        Alternative endpoint to process an image and return extracted data
        without necessarily saving it
        """
        image_file = request.FILES.get('image')
        
        if not image_file:
            return Response(
                {'error': 'No image provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            extracted_data = process_citizenship_image(image_file)
            return Response(
                extracted_data,
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            return Response(
                {'error': f'Error processing image: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
