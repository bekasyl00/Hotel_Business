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
from commerce.accounting.views import AccountingView, BookingDocumentsView, GuestDocumentsView
from commerce.payment_views import HalykCallbackView, PaymentView
from commerce.scheduler import tick
from commerce.views import CancellationPreviewView, DemoPaymentView, ReceiptView
from commerce.xpayment_webhook import XPaymentCallbackView

from .health import live, ready

api_patterns = [
    path("accounting/report.xlsx", AccountingView.as_view(), {"resource": "report"}),
    path("accounting/expenses", AccountingView.as_view(), {"resource": "expenses"}),
    path("accounting/expenses/<str:pk>/void", AccountingView.as_view(), {"resource": "expenses"}),
    path("bookings/<str:booking_id>/documents", BookingDocumentsView.as_view()),
    path(
        "bookings/<str:booking_id>/documents/<str:pk>/<str:format_kind>/download",
        BookingDocumentsView.as_view(),
    ),
    path("accounting", AccountingView.as_view()),
    path("accounting/export", AccountingView.as_view(), {"resource": "export"}),
    path("accounting/company/<str:pk>", AccountingView.as_view(), {"resource": "company"}),
    path("accounting/documents", AccountingView.as_view(), {"resource": "documents"}),
    path(
        "accounting/documents/<str:pk>/<str:format_kind>/download",
        AccountingView.as_view(),
        {"resource": "file"},
    ),
    path(
        "accounting/documents/<str:pk>/<str:action>",
        AccountingView.as_view(),
        {"resource": "documents"},
    ),
    path("my-documents", GuestDocumentsView.as_view()),
    path("my-documents/<str:pk>/<str:format_kind>/download", GuestDocumentsView.as_view()),
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
        r"^(?P<resource>bookings)/(?P<pk>[^/]+)/(?P<action>check-in|check-out|notes)$",
        Endpoint.as_view(),
    ),
    path("payments/config", PaymentView.as_view()),
    path("payments/checkouts", PaymentView.as_view()),
    path("payments/staff/checkouts", PaymentView.as_view(), {"staff": True}),
    path("payments/providers/halyk/callback", HalykCallbackView.as_view()),
    path("payments/providers/xpayment/callback", XPaymentCallbackView.as_view()),
    path("payments/staff/<str:pk>/refresh", PaymentView.as_view(), {"staff": True}),
    path("payments/staff/<str:pk>", PaymentView.as_view(), {"staff": True}),
    path("payments/<str:pk>/refresh", PaymentView.as_view()),
    path("payments/demo", DemoPaymentView.as_view()),
    path("payments/demo/staff", DemoPaymentView.as_view(), {"staff": True}),
    path("payments/<str:pk>", PaymentView.as_view()),
    path("receipts/<str:pk>/pdf", ReceiptView.as_view(), {"pdf": True}),
    path("receipts/<str:pk>", ReceiptView.as_view()),
    path("cancellation-preview/<str:pk>", CancellationPreviewView.as_view()),
    re_path(r"^(?P<resource>auth/(?:csrf|session|login|logout))$", Endpoint.as_view()),
    path("<str:resource>", Endpoint.as_view()),
    path("<str:resource>/<str:pk>", Endpoint.as_view()),
]
urlpatterns = [
    path("internal/payments/tick", tick),
    path("health/live", live),
    path("health/ready", ready),
    path("django-admin/", platform_admin_site.urls),
    path("admin/", RedirectView.as_view(url="/django-admin/", permanent=False)),
    path("api/v1/", include(api_patterns)),
    path("api/", include(api_patterns)),
]
# Old illustrative uploads only. New files are served by the authorized MediaFile view.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.LEGACY_MEDIA_ROOT)
