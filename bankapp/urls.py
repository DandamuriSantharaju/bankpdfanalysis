from django.urls import path
from .views import UploadPDFView

urlpatterns = [
    path('upload/', UploadPDFView.as_view(), name='upload-pdf')  # ✅ CORRECT
]
