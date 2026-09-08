import math
from decimal import Decimal, ROUND_HALF_UP


def classify_tier(item_value, case_price):
    """
    Classifies an item into an exciting visual risk tier based on multiplier:
    - Jackpot: >= 8x case price
    - Legendary: >= 4x case price
    - Epic: >= 2x case price
    - Rare: >= 1x case price
    - Uncommon: >= 0.4x case price
    - Common: < 0.4x case price
    """
    val = float(item_value)
    price = float(case_price)
    if price <= 0:
        return 'Common'
    
    ratio = val / price
    if ratio >= 8.0:
        return 'Jackpot'
    elif ratio >= 4.0:
        return 'Legendary'
    elif ratio >= 2.0:
        return 'Epic'
    elif ratio >= 1.0:
        return 'Rare'
    elif ratio >= 0.4:
        return 'Uncommon'
    else:
        return 'Common'


def calculate_rtp_chances(items, case_price, target_rtp=0.90, mode='balanced'):
    """
    Calculates recommended drop chances for a set of items such that:
    1. Expected Return = sum(p_i * value_i) = case_price * target_rtp
    2. Sum of all probabilities = 100.000%
    3. Every probability > 0%
    
    Parameters:
    - items: list of dicts [{'id': ..., 'name': ..., 'value': Decimal|float}, ...]
    - case_price: Decimal or float (price to open case)
    - target_rtp: float (e.g. 0.90 for 90% return-to-player)
    - mode: 'balanced' or 'high_volatility' (more frequent low wins, rarer jackpots)
    
    Returns:
    - dict with 'items' (with 'chance', 'weight', 'tier'), 'expected_return',
      'target_return', 'calculated_rtp', 'house_edge', 'total_probability'
    """
    if not items:
        raise ValueError("Item list cannot be empty.")
    
    price = float(case_price)
    if price <= 0:
        raise ValueError("Case price must be greater than zero.")
    
    rtp = float(target_rtp)
    if not (0.10 <= rtp <= 1.50):
        raise ValueError("Target RTP must be between 10% and 150%.")
    
    target_ev = price * rtp
    n = len(items)
    
    # Extract values and ensure positive (support both 'value' and 'price' keys)
    values = []
    for it in items:
        val = it.get('value') if it.get('value') is not None else it.get('price')
        if val is None:
            val = 1.0
        values.append(max(0.10, float(val)))

    min_v = min(values)
    max_v = max(values)
    
    # Check if target EV is mathematically reachable
    if target_ev < min_v:
        # Even if 100% chance is on min item, EV is >= min_v
        target_ev = min_v
    elif target_ev > max_v:
        target_ev = max_v
    
    # Base power parameter depending on mode
    # Higher beta = stronger penalty on expensive items = more volatile
    is_volatile = mode in ('volatile', 'high_volatility')
    base_beta = 1.45 if is_volatile else 1.05
    
    # We solve for parameter lambda in: p_i(lambda) proportional to (1 / v_i^base_beta) * exp(-lambda * v_i)
    # such that sum(p_i * v_i) == target_ev
    def get_ev_for_lambda(lam):
        raw_weights = []
        for v in values:
            w = (1.0 / (v ** base_beta)) * math.exp(-lam * (v / price))
            raw_weights.append(w)
        total_w = sum(raw_weights)
        if total_w <= 0:
            return target_ev, [1.0 / n] * n
        probs = [w / total_w for w in raw_weights]
        ev = sum(p * v for p, v in zip(probs, values))
        return ev, probs
    
    # Binary search for lambda
    low_lam, high_lam = -20.0, 30.0
    best_probs = [1.0 / n] * n
    
    for _ in range(60):
        mid_lam = (low_lam + high_lam) / 2.0
        ev, probs = get_ev_for_lambda(mid_lam)
        best_probs = probs
        if abs(ev - target_ev) < 0.0001:
            break
        if ev > target_ev:
            # We want smaller EV -> need higher lambda (penalize higher v)
            low_lam = mid_lam
        else:
            high_lam = mid_lam

    if mode in ('monotonic', 'power_law'):
        low_alpha, high_alpha = 0.0, 10.0
        for _ in range(60):
            mid_alpha = (low_alpha + high_alpha) / 2.0
            raw_w = [v ** (-mid_alpha) for v in values]
            t_w = sum(raw_w)
            if t_w > 0:
                p_list = [w / t_w for w in raw_w]
                ev = sum(p * v for p, v in zip(p_list, values))
                if ev > target_ev:
                    low_alpha = mid_alpha
                else:
                    high_alpha = mid_alpha
                best_probs = p_list
            
    # Convert probabilities to percentage with 3 decimal places (e.g. 15.250%)
    # Ensure minimum chance of 0.010% for excitement
    raw_percentages = [max(0.010, p * 100.0) for p in best_probs]
    total_raw = sum(raw_percentages)
    normalized = [(p / total_raw) * 100.0 for p in raw_percentages]
    
    # Round to 3 decimal places and fix rounding residue on the lowest item
    rounded = [round(p, 3) for p in normalized]
    diff = round(100.0 - sum(rounded), 3)
    
    # Add difference to the most common (lowest value) item
    min_idx = values.index(min_v)
    rounded[min_idx] = round(rounded[min_idx] + diff, 3)
    
    # Double check total is strictly 100.000
    final_total = round(sum(rounded), 3)
    if final_total != 100.0:
        rounded[min_idx] += round(100.0 - final_total, 3)
        
    # Build detailed result list and tier summary
    result_items = []
    actual_ev = 0.0
    tier_summary = {
        'Jackpot': {'count': 0, 'total_chance_pct': 0.0, 'min_value': float('inf'), 'max_value': 0.0, 'tier_class': 'jackpot'},
        'Legendary': {'count': 0, 'total_chance_pct': 0.0, 'min_value': float('inf'), 'max_value': 0.0, 'tier_class': 'legendary'},
        'Epic': {'count': 0, 'total_chance_pct': 0.0, 'min_value': float('inf'), 'max_value': 0.0, 'tier_class': 'epic'},
        'Rare': {'count': 0, 'total_chance_pct': 0.0, 'min_value': float('inf'), 'max_value': 0.0, 'tier_class': 'rare'},
        'Uncommon': {'count': 0, 'total_chance_pct': 0.0, 'min_value': float('inf'), 'max_value': 0.0, 'tier_class': 'uncommon'},
        'Common': {'count': 0, 'total_chance_pct': 0.0, 'min_value': float('inf'), 'max_value': 0.0, 'tier_class': 'common'},
    }
    
    for i, it in enumerate(items):
        v = values[i]
        p = rounded[i]
        ev_contrib = (p / 100.0) * v
        actual_ev += ev_contrib
        tier = classify_tier(v, price)
        
        item_copy = dict(it)
        item_copy['chance'] = p
        item_copy['chance_pct'] = p
        item_copy['weight'] = p # Weight in CaseItem equals chance percent
        item_copy['tier'] = tier
        item_copy['tier_class'] = tier.lower()
        item_copy['value'] = round(v, 2)
        item_copy['price'] = round(v, 2)
        item_copy['expected_contribution'] = round(ev_contrib, 3)
        result_items.append(item_copy)

        # Tier breakdown stats
        t_stat = tier_summary.get(tier)
        if t_stat:
            t_stat['count'] += 1
            t_stat['total_chance_pct'] = round(t_stat['total_chance_pct'] + p, 3)
            t_stat['min_value'] = min(t_stat['min_value'], v)
            t_stat['max_value'] = max(t_stat['max_value'], v)

    for t_stat in tier_summary.values():
        if t_stat['min_value'] == float('inf'):
            t_stat['min_value'] = 0.0
        
    actual_rtp = (actual_ev / price) if price > 0 else 0.0
    house_edge = max(0.0, 1.0 - actual_rtp)
    
    return {
        'items': result_items,
        'case_price': round(price, 2),
        'target_rtp': round(rtp * 100.0, 2),
        'calculated_rtp': round(actual_rtp * 100.0, 2),
        'actual_rtp': round(actual_rtp * 100.0, 2),
        'expected_return': round(actual_ev, 2),
        'house_edge': round(house_edge * 100.0, 2),
        'total_prob': 100.000,
        'total_probability': 100.000,
        'tier_summary': tier_summary,
        'mode': mode
    }


class InvalidChancesError(ValueError):
    """Raised when case item weights or chances are invalid or do not sum to 100%."""
    pass


def validate_case_chances(case_items, raise_exception=True):
    """
    Strict validator:
    - All chances > 0
    - No negative numbers
    - Sum equals exactly 100.000% (within 0.01 tolerance)
    """
    items_list = list(case_items) if hasattr(case_items, '__iter__') else []
    if not items_list:
        msg = "В кейсе нет предметов."
        if raise_exception:
            raise InvalidChancesError(msg)
        return False, msg
        
    total = 0.0
    for it in items_list:
        if isinstance(it, dict):
            w = float(it.get('chance') or it.get('weight') or it.get('chance_pct') or 0.0)
            name = it.get('name', 'Без имени')
        else:
            w = float(getattr(it, 'weight', 0.0) or 0.0)
            name = getattr(getattr(it, 'item', None), 'name', str(it))

        if w <= 0:
            msg = f"Предмет {name} имеет недопустимый шанс/вес {w}%."
            if raise_exception:
                raise InvalidChancesError(msg)
            return False, msg
        total += w
        
    if abs(total - 100.0) > 0.05:
        msg = f"Сумма шансов равна {round(total, 3)}%, а должна быть ровно 100.000%."
        if raise_exception:
            raise InvalidChancesError(msg)
        return False, msg
        
    return True, "Конфигурация шансов корректна."
