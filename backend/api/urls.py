from django.urls import path
from .views import PayoutRequestView, MerchantListView

urlpatterns = [
    path('merchants/', MerchantListView.as_view(), name='merchant-list'),
    path('payouts/', PayoutRequestView.as_view(), name='payout-request'),
]
