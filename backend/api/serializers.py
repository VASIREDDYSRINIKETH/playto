from rest_framework import serializers
from .models import Merchant, Payout

class PayoutCreateSerializer(serializers.Serializer):
    merchant = serializers.UUIDField()
    amount = serializers.IntegerField(min_value=1)  # Amount in paise

class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = ['id', 'merchant', 'amount', 'status', 'created_at']

class MerchantSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Merchant
        fields = ['id', 'name', 'balance']

    def get_balance(self, obj):
        return obj.get_balance()
