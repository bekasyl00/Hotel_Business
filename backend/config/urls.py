from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, re_path

from booking.guest_auth import GuestAuthView
from booking.media import MediaUpload
from booking.views import Endpoint
from commerce.views import CancellationPreviewView, DemoPaymentView, ReceiptView

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/media", MediaUpload.as_view()),
    path("api/guest-auth/<str:action>", GuestAuthView.as_view()),
    re_path(
        r"^api/(?P<resource>bookings)/(?P<pk>[^/]+)/(?P<action>check-in|check-out)$",
        Endpoint.as_view(),
    ),
    path("api/payments/demo", DemoPaymentView.as_view()),
    path("api/receipts/<str:pk>/pdf", ReceiptView.as_view(), {"pdf": True}),
    path("api/receipts/<str:pk>", ReceiptView.as_view()),
    path("api/cancellation-preview/<str:pk>", CancellationPreviewView.as_view()),
    re_path(r"^api/(?P<resource>auth/(?:csrf|session|login|logout))$", Endpoint.as_view()),
    path("api/<str:resource>", Endpoint.as_view()),
    path("api/<str:resource>/<str:pk>", Endpoint.as_view()),
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
