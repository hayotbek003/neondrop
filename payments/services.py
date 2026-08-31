from decimal import Decimal
import logging
from django.db import transaction
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import Transaction
from users.models import Profile

audit_logger = logging.getLogger('neondrop.audit')
security_logger = logging.getLogger('neondrop.security')

class InsufficientBalanceError(Exception):
    """Raised when a user attempts an operation with insufficient funds."""
    pass

@transaction.atomic
def modify_user_balance(
    user: User,
    amount_delta: Decimal,
    transaction_type: str,
    reference_id: str = '',
    description: str = '',
    payment_method: str = 'system',
    idempotency_key: str = None,
    ip_address: str = None,
    admin_user: User = None
) -> Transaction:
    """
    Authoritative server-side balance modification with atomic row locking and immutable ledger recording.
    
    :param user: The User whose balance is being changed.
    :param amount_delta: Decimal amount (positive to credit, negative to debit).
    :param transaction_type: Category choice from Transaction.TYPE_CHOICES.
    :param reference_id: Identifier of related entity (e.g. 'case:5', 'opening:12').
    :param description: Human-readable audit text.
    :param payment_method: Payment rail / channel.
    :param idempotency_key: Optional request deduplication token.
    :param ip_address: Originating client IP.
    :param admin_user: If modified by an administrator, the performing staff user.
    :return: Created Transaction instance.
    :raises: InsufficientBalanceError if debit exceeds current balance.
    """
    # 1. Lock user profile record with select_for_update
    profile = Profile.objects.select_for_update().get(user=user)
    
    balance_before = profile.balance
    new_balance = balance_before + amount_delta
    
    # 2. Strict validation: balance must never be negative
    if new_balance < Decimal('0.00'):
        security_logger.warning(
            f"Insufficient balance attempt: user={user.username} (id={user.id}), "
            f"current=${balance_before}, attempted_delta=${amount_delta}, required=${abs(amount_delta)}"
        )
        raise InsufficientBalanceError(
            f"Недостаточно средств. Ваш баланс: ${balance_before:.2f}, требуется: ${abs(amount_delta):.2f}"
        )
    
    # 3. Apply balance modification
    profile.balance = new_balance
    profile.save(update_fields=['balance'])
    
    # 4. Create immutable Transaction ledger record
    admin_note = f" (Выполнено админом: {admin_user.username})" if admin_user else ""
    tx = Transaction.objects.create(
        user=user,
        amount=amount_delta,
        balance_before=balance_before,
        balance_after=new_balance,
        transaction_type=transaction_type,
        status='completed',
        payment_method=payment_method,
        reference_id=reference_id,
        description=f"{description}{admin_note}".strip(),
        idempotency_key=idempotency_key,
        ip_address=ip_address
    )
    
    # 5. Emit security audit log
    audit_logger.info(
        f"BALANCE_MUTATION: user={user.username} (id={user.id}) | "
        f"type={transaction_type} | delta={amount_delta:+.2f} | "
        f"before=${balance_before:.2f} -> after=${new_balance:.2f} | "
        f"ref={reference_id} | tx_id={tx.id} | ip={ip_address}"
    )
    
    return tx
