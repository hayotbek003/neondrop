import hashlib
import hmac
import secrets
from typing import List, Tuple, Any, Dict, Optional
from decimal import Decimal
from django.utils import timezone

def generate_server_seed() -> str:
    """Generate a cryptographically secure 64-char hex string server seed."""
    return secrets.token_hex(32)

def hash_seed(seed: str) -> str:
    """Generate SHA256 hash of a seed."""
    return hashlib.sha256(seed.encode('utf-8')).hexdigest()

def calculate_provably_fair_roll(server_seed: str, client_seed: str, nonce: int) -> float:
    """
    Calculate provably fair float between 0.0 (inclusive) and 1.0 (exclusive)
    using HMAC-SHA256 of server_seed, client_seed, and nonce.
    """
    message = f"{client_seed}:{nonce}".encode('utf-8')
    key = server_seed.encode('utf-8')
    h = hmac.new(key, message, hashlib.sha256).hexdigest()
    
    # Take the first 8 hex characters (32 bits) and convert to int
    first_8_chars = h[:8]
    val = int(first_8_chars, 16)
    
    # Divide by 2^32 (4294967296) to get float in [0, 1)
    return val / 4294967296.0

def get_effective_case_chances(case: Any, user: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Calculate normalized item probabilities for a case, factoring in active PersonalCaseChance
    for the given user if present. Guarantees the sum of probabilities is strictly 1.0 (100%).
    """
    from .models import PersonalCaseChance
    
    case_items = list(case.case_items.select_related('item').all())
    if not case_items:
        return []

    total_base_weight = sum(ci.weight for ci in case_items)
    if total_base_weight <= 0:
        total_base_weight = 1.0

    # 1. Check for active Personal Case Chance for this user & case
    active_promo = None
    if user and user.is_authenticated:
        now = timezone.now()
        active_promo = PersonalCaseChance.objects.filter(
            user=user,
            case=case,
            is_active=True,
            starts_at__lte=now,
            expires_at__gte=now
        ).select_related('item').first()

    results = []

    if active_promo:
        target_item_id = active_promo.item_id
        promoted_prob = float(active_promo.chance) / 100.0
        promoted_prob = max(0.0001, min(0.9999, promoted_prob))
        remaining_prob_budget = 1.0 - promoted_prob

        other_items = [ci for ci in case_items if ci.item_id != target_item_id]
        other_weight_sum = sum(ci.weight for ci in other_items)

        for ci in case_items:
            if ci.item_id == target_item_id:
                prob = promoted_prob
                is_promoted = True
            else:
                if other_weight_sum > 0:
                    prob = remaining_prob_budget * (ci.weight / other_weight_sum)
                else:
                    prob = remaining_prob_budget / max(1, len(other_items))
                is_promoted = False

            results.append({
                'case_item': ci,
                'item': ci.item,
                'probability': prob,
                'chance_percent': round(prob * 100.0, 2),
                'is_promoted': is_promoted,
            })
    else:
        for ci in case_items:
            prob = ci.weight / total_base_weight
            results.append({
                'case_item': ci,
                'item': ci.item,
                'probability': prob,
                'chance_percent': round(prob * 100.0, 2),
                'is_promoted': False,
            })

    return results

def select_weighted_item(case_items: List[Any], server_seed: str, client_seed: str, nonce: int, user: Optional[Any] = None, case: Optional[Any] = None):
    """
    Select an item from case_items based on normalized weights / personal chances using provably fair roll.
    Returns: (selected_case_item, roll_float, server_seed_hash)
    """
    server_seed_hash = hash_seed(server_seed)
    roll = calculate_provably_fair_roll(server_seed, client_seed, nonce)

    if not case_items:
        raise ValueError("Case items list cannot be empty.")

    if case is None and case_items:
        case = case_items[0].case

    if case:
        entries = get_effective_case_chances(case, user)
        if entries:
            cumulative = 0.0
            for entry in entries:
                cumulative += entry['probability']
                if roll <= cumulative:
                    return entry['case_item'], roll, server_seed_hash
            return entries[-1]['case_item'], roll, server_seed_hash

    # Fallback standard selection
    total_weight = sum(ci.weight for ci in case_items)
    if total_weight <= 0:
        return case_items[0], roll, server_seed_hash
        
    target = roll * total_weight
    cumulative = 0.0
    
    for ci in case_items:
        cumulative += ci.weight
        if target <= cumulative:
            return ci, roll, server_seed_hash
            
    return case_items[-1], roll, server_seed_hash
