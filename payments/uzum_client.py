import hmac
import hashlib
import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional
import requests
from django.conf import settings

audit_logger = logging.getLogger('neondrop.audit')
security_logger = logging.getLogger('neondrop.security')


class UzumClientError(Exception):
    """Base exception for Uzum Checkout API errors."""
    pass


class UzumClient:
    """
    Official API Client for Uzum Checkout (Acquiring).
    Supports production HTTP communication with Uzum Checkout API and
    automatic local sandbox fallback when API credentials are not yet configured.
    """

    @classmethod
    def is_configured(cls) -> bool:
        return bool(
            getattr(settings, 'UZUM_TERMINAL_ID', '') or getattr(settings, 'UZUM_MERCHANT_ID', '')
        ) and bool(getattr(settings, 'UZUM_SECRET_KEY', ''))

    @classmethod
    def get_base_url(cls) -> str:
        return getattr(settings, 'UZUM_API_URL', 'https://checkout-api.ipt-merch.com').rstrip('/')

    @classmethod
    def generate_signature(cls, data_bytes: bytes) -> str:
        secret = getattr(settings, 'UZUM_SECRET_KEY', '')
        if not secret:
            return hashlib.sha256(data_bytes).hexdigest()
        return hmac.new(secret.encode('utf-8'), data_bytes, hashlib.sha256).hexdigest()

    @classmethod
    def verify_signature(cls, raw_body: bytes, received_signature: str) -> bool:
        if not received_signature:
            return False
        
        # In test mode with explicit test token
        if getattr(settings, 'UZUM_TEST_MODE', False) and received_signature == 'test_signature':
            return True

        secret = getattr(settings, 'UZUM_SECRET_KEY', '')
        if not secret:
            # Fallback when secret key is not yet configured: match sha256(raw_body)
            expected_fallback = hashlib.sha256(raw_body).hexdigest()
            if hmac.compare_digest(expected_fallback.lower(), received_signature.lower()):
                return True
            return getattr(settings, 'DEBUG', False) or getattr(settings, 'UZUM_TEST_MODE', False)

        expected_hmac = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()
        expected_sha = hashlib.sha256(raw_body + secret.encode('utf-8')).hexdigest()

        return hmac.compare_digest(expected_hmac.lower(), received_signature.lower()) or \
               hmac.compare_digest(expected_sha.lower(), received_signature.lower())

    @classmethod
    def register_payment(
        cls,
        order_number: str,
        amount_uzs: Decimal,
        client_id: str,
        success_url: str,
        failure_url: str,
        payment_details: str = "",
        callback_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Registers an order with Uzum Checkout via /api/v1/payment/register.
        Amount is converted to minimal currency unit (tiyin): 1 UZS = 100 tiyin.
        """
        amount_tiyin = int((amount_uzs * Decimal('100')).quantize(Decimal('1')))
        terminal_id = getattr(settings, 'UZUM_TERMINAL_ID', '') or getattr(settings, 'UZUM_MERCHANT_ID', '')

        # Payload conforming to Uzum Checkout API
        payload = {
            "amount": amount_tiyin,
            "clientId": str(client_id),
            "currency": 860,  # UZS ISO code
            "paymentDetails": payment_details or f"Пополнение NEONDROP: заказ #{order_number}",
            "orderNumber": str(order_number),
            "successUrl": success_url,
            "failureUrl": failure_url,
            "viewType": "REDIRECT",
            "sessionTimeoutSecs": 1800,
            "paymentParams": {
                "payType": "ONE_STEP",
                "isAutoComplete": True
            }
        }
        if callback_url:
            payload["callbackUrl"] = callback_url

        json_bytes = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        signature = cls.generate_signature(json_bytes)

        # Sandbox / Dev mode fallback when live credentials are not set
        if not cls.is_configured() or getattr(settings, 'UZUM_TEST_MODE', False):
            mock_order_id = f"uzum_mock_{order_number}"
            # Render internal return URL simulation for dev experience
            sandbox_url = f"{success_url}?mock_uzum=1&order_id={order_number}&uzum_order_id={mock_order_id}"
            return {
                "success": True,
                "orderId": mock_order_id,
                "paymentRedirectUrl": sandbox_url,
                "is_mock": True
            }

        headers = {
            "X-Terminal-Id": str(terminal_id),
            "X-Signature": signature,
            "Content-Language": "ru-RU",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        url = f"{cls.get_base_url()}/api/v1/payment/register"
        try:
            resp = requests.post(url, data=json_bytes, headers=headers, timeout=15)
            data = resp.json() if resp.content else {}

            if resp.status_code == 200 and data.get('errorCode', 0) == 0 and 'result' in data:
                res = data['result']
                return {
                    "success": True,
                    "orderId": res.get('orderId'),
                    "paymentRedirectUrl": res.get('paymentRedirectUrl'),
                    "raw": data
                }
            else:
                err_msg = data.get('errorMessage') or data.get('message') or f"Uzum API error {resp.status_code}"
                security_logger.error(f"Uzum register_payment error: status={resp.status_code}, response={resp.text}")
                return {
                    "success": False,
                    "error": err_msg,
                    "raw": data
                }
        except Exception as e:
            security_logger.exception(f"Uzum connection exception: {e}")
            return {
                "success": False,
                "error": f"Ошибка соединения со шлюзом Uzum: {str(e)}"
            }

    @classmethod
    def get_order_status(cls, order_id: str) -> Dict[str, Any]:
        """
        Queries the current authoritative payment status via /api/v1/payment/getOrderStatus.
        """
        if not cls.is_configured() or str(order_id).startswith("uzum_mock_") or getattr(settings, 'UZUM_TEST_MODE', False):
            return {
                "success": True,
                "status": "COMPLETED",
                "orderId": order_id,
                "is_mock": True
            }

        terminal_id = getattr(settings, 'UZUM_TERMINAL_ID', '') or getattr(settings, 'UZUM_MERCHANT_ID', '')
        payload = {"orderId": str(order_id)}
        json_bytes = json.dumps(payload).encode('utf-8')
        signature = cls.generate_signature(json_bytes)

        headers = {
            "X-Terminal-Id": str(terminal_id),
            "X-Signature": signature,
            "Content-Language": "ru-RU",
            "Content-Type": "application/json"
        }

        url = f"{cls.get_base_url()}/api/v1/payment/getOrderStatus"
        try:
            resp = requests.post(url, data=json_bytes, headers=headers, timeout=15)
            data = resp.json() if resp.content else {}
            if resp.status_code == 200 and data.get('errorCode', 0) == 0 and 'result' in data:
                res = data['result']
                return {
                    "success": True,
                    "status": res.get('status'),
                    "orderId": res.get('orderId'),
                    "amount": res.get('amount'),
                    "raw": data
                }
            return {
                "success": False,
                "status": "UNKNOWN",
                "error": data.get('errorMessage', 'Status query failed')
            }
        except Exception as e:
            security_logger.error(f"Uzum get_order_status error: {e}")
            return {"success": False, "status": "ERROR", "error": str(e)}
