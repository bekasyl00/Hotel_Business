from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from booking.admin import platform_admin_site
from booking.guest_auth import GuestAuthView
from booking.media import MediaFile, MediaUpload, ProfileAvatar
from booking.mobile_auth import MobileAuthView, MobileSessionView
from booking.staff_mobile_auth import StaffMobileAuthView, StaffMobileSessionView
from booking.views import Endpoint
from commerce.views import CancellationPreviewView, DemoPaymentView, ReceiptView

from .health import live, ready

api_patterns = [
    path("staff-mobile-auth/sessions", StaffMobileSessionView.as_view()),
    path("staff-mobile-auth/sessions/<uuid:pk>", StaffMobileSessionView.as_view()),
    path("staff-mobile-auth/<str:action>", StaffMobileAuthView.as_view()),
    path("media", MediaUpload.as_view()),
    path("media/files/<uuid:pk>", MediaFile.as_view()),
    path("profile/avatar", ProfileAvatar.as_view()),
    path("guest-auth/<str:action>", GuestAuthView.as_view()),
    path("mobile-auth/sessions", MobileSessionView.as_view()),
    path("mobile-auth/sessions/<uuid:pk>", MobileSessionView.as_view()),
    path("mobile-auth/<str:action>", MobileAuthView.as_view()),
    re_path(
        r"^(?P<resource>bookings)/(?P<pk>[^/]+)/(?P<action>check-in|check-out)$",
        Endpoint.as_view(),
    ),
    path("payments/demo", DemoPaymentView.as_view()),
    path("receipts/<str:pk>/pdf", ReceiptView.as_view(), {"pdf": True}),
    path("receipts/<str:pk>", ReceiptView.as_view()),
    path("cancellation-preview/<str:pk>", CancellationPreviewView.as_view()),
    re_path(r"^(?P<resource>auth/(?:csrf|session|login|logout))$", Endpoint.as_view()),
    path("<str:resource>", Endpoint.as_view()),
    path("<str:resource>/<str:pk>", Endpoint.as_view()),
]
urlpatterns = [
    path("health/live", live),
    path("health/ready", ready),
    path("django-admin/", platform_admin_site.urls),
    path("admin/", RedirectView.as_view(url="/django-admin/", permanent=False)),
    path("api/v1/", include(api_patterns)),
    path("api/", include(api_patterns)),
]
# Old illustrative uploads only. New files are served by the authorized MediaFile view.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.LEGACY_MEDIA_ROOT)
