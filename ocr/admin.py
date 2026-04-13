from django.contrib import admin
from .models import CitizenshipDocument


@admin.register(CitizenshipDocument)
class CitizenshipDocumentAdmin(admin.ModelAdmin):
    list_display = ('citizenship_no', 'name', 'gender', 'district', 'created_at')
    list_filter = ('created_at', 'gender', 'district', 'municipality')
    search_fields = ('citizenship_no', 'name', 'father', 'mother')
    readonly_fields = ('created_at', 'updated_at', 'raw_text')
    
    fieldsets = (
        ('Document Image', {
            'fields': ('image',)
        }),
        ('Personal Information', {
            'fields': ('citizenship_no', 'name', 'gender', 'dob')
        }),
        ('Address Information', {
            'fields': ('district', 'birth_district', 'municipality', 'ward', 'vdc_area', 'full_address')
        }),
        ('Family Information', {
            'fields': ('father', 'mother')
        }),
        ('Document Information', {
            'fields': ('office', 'document_type')
        }),
        ('OCR Data', {
            'fields': ('raw_text',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
