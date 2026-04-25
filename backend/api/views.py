import json
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError

from .models import IdempotencyKey, Merchant, Payout
from .serializers import PayoutCreateSerializer, PayoutSerializer, MerchantSerializer
from .services import initiate_payout
from .tasks import process_payout_task

class MerchantListView(APIView):
    def get(self, request):
        merchants = Merchant.objects.all()
        serializer = MerchantSerializer(merchants, many=True)
        return Response(serializer.data)

class PayoutRequestView(APIView):
    def post(self, request):
        idempotency_key = request.headers.get('Idempotency-Key')
        if not idempotency_key:
            return Response(
                {"error": "Idempotency-Key header is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 1. Idempotency Check with Lock
        with transaction.atomic():
            # We attempt to create the idempotency record or fetch and lock it
            idemp_obj, created = IdempotencyKey.objects.get_or_create(
                key=idempotency_key,
                defaults={'request_path': request.path}
            )
            if not created:
                # We need to lock it to prevent race conditions during concurrent retry
                idemp_obj = IdempotencyKey.objects.select_for_update().get(key=idempotency_key)
                
            if not created and idemp_obj.response_status is not None:
                # We already processed this, return cached response!
                return Response(idemp_obj.response_body, status=idemp_obj.response_status)
            
            if not created and idemp_obj.response_status is None:
                # It's currently being processed by another thread
                return Response(
                    {"error": "A request with this Idempotency-Key is currently being processed."},
                    status=status.HTTP_409_CONFLICT
                )

        # 2. Synchronous Validation and Processing
        serializer = PayoutCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return self._finalize_response(idempotency_key, serializer.errors, status.HTTP_400_BAD_REQUEST)

        try:
            payout = initiate_payout(
                merchant_id=serializer.validated_data['merchant'],
                amount=serializer.validated_data['amount']
            )
        except ValidationError as e:
            return self._finalize_response(idempotency_key, e.detail, status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return self._finalize_response(idempotency_key, {"error": str(e)}, status.HTTP_500_INTERNAL_SERVER_ERROR)

        response_data = PayoutSerializer(payout).data
        
        # Dispatch background task immediately after successful sync layer
        # Because we only dispatch if no exception raised, it's safe.
        from django_q.tasks import async_task
        transaction.on_commit(lambda: async_task(process_payout_task, str(payout.id)))

        return self._finalize_response(idempotency_key, response_data, status.HTTP_201_CREATED)

    def _finalize_response(self, idempotency_key, response_data, status_code):
        """Helper to save the result back into the idempotency key and return response"""
        import json
        from django.core.serializers.json import DjangoJSONEncoder
        safe_data = json.loads(json.dumps(response_data, cls=DjangoJSONEncoder))
        
        with transaction.atomic():
            idemp_obj = IdempotencyKey.objects.select_for_update().get(key=idempotency_key)
            idemp_obj.response_status = status_code
            idemp_obj.response_body = safe_data
            idemp_obj.save(update_fields=['response_status', 'response_body'])
            
        return Response(response_data, status=status_code)
