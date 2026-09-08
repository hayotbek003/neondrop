import hashlib
import hmac
import math
import secrets
import bisect
from decimal import Decimal
from typing import Dict, Any, Optional

from django.contrib.auth.models import User
from .models import Case, RngSimulationRun
from .provably_fair import generate_server_seed, hash_seed

try:
    from scipy import stats as scipy_stats
except ImportError:
    scipy_stats = None


def _chi_square_p_value(chi2: float, df: int) -> float:
    if scipy_stats is not None:
        try:
            return float(scipy_stats.chi2.sf(chi2, df))
        except Exception:
            pass

    if chi2 <= 0:
        return 1.0
    if df <= 0:
        return 0.0

    k = df / 2.0
    x = chi2 / 2.0
    return _gammp_upper(k, x)


def _gammp_upper(a: float, x: float) -> float:
    if x < a + 1.0:
        ap = a
        sum_val = 1.0 / a
        del_val = sum_val
        for _ in range(300):
            ap += 1.0
            del_val *= x / ap
            sum_val += del_val
            if abs(del_val) < abs(sum_val) * 1e-12:
                break
        gln = math.lgamma(a)
        p = sum_val * math.exp(-x + a * math.log(x) - gln)
        return max(0.0, min(1.0, 1.0 - p))
    else:
        b = x + 1.0 - a
        c = 1.0 / 1e-30
        d = 1.0 / b
        h = d
        for i in range(1, 300):
            an = -i * (i - a)
            b += 2.0
            d = an * d + b
            if abs(d) < 1e-30:
                d = 1e-30
            c = b + an / c
            if abs(c) < 1e-30:
                c = 1e-30
            d = 1.0 / d
            del_val = d * c
            h *= del_val
            if abs(del_val - 1.0) < 1e-12:
                break
        gln = math.lgamma(a)
        q = math.exp(-x + a * math.log(x) - gln) * h
        return max(0.0, min(1.0, q))


def run_monte_carlo_simulation(
    case: Case,
    num_simulations: int = 100000,
    user: Optional[User] = None,
    server_seed: Optional[str] = None,
    client_seed: Optional[str] = None,
    save_run: bool = True
) -> Dict[str, Any]:
    if num_simulations not in [1000, 10000, 100000, 1000000]:
        num_simulations = max(100, min(1000000, int(num_simulations)))

    case_items = list(case.case_items.select_related('item').all())
    if not case_items:
        raise ValueError(f"Кейс '{case.name}' не содержит предметов для симуляции.")

    total_base_weight = sum(ci.weight for ci in case_items)
    if total_base_weight <= 0:
        total_base_weight = 1.0

    probs = [ci.weight / total_base_weight for ci in case_items]
    
    cum_probs = []
    running = 0.0
    for p in probs:
        running += p
        cum_probs.append(running)
    cum_probs[-1] = 1.0

    case_price = float(case.price)
    item_prices = [float(ci.item.value) for ci in case_items]

    target_ev = sum(p * val for p, val in zip(probs, item_prices))
    target_rtp = (target_ev / case_price * 100.0) if case_price > 0 else 0.0
    target_house_edge = max(0.0, 100.0 - target_rtp)

    if not server_seed:
        server_seed = generate_server_seed()
    if not client_seed:
        client_seed = secrets.token_hex(16)

    key_bytes = server_seed.encode('utf-8')
    client_seed_str = str(client_seed)

    k_items = len(case_items)
    drop_counts = [0] * k_items

    for nonce in range(1, num_simulations + 1):
        msg = f"{client_seed_str}:{nonce}".encode('utf-8')
        h = hmac.new(key_bytes, msg, hashlib.sha256).hexdigest()
        val = int(h[:8], 16)
        roll = val / 4294967296.0

        idx = bisect.bisect_left(cum_probs, roll)
        if idx >= k_items:
            idx = k_items - 1
        drop_counts[idx] += 1

    total_spent = num_simulations * case_price
    total_payout = sum(count * price for count, price in zip(drop_counts, item_prices))
    actual_rtp = (total_payout / total_spent * 100.0) if total_spent > 0 else 0.0
    deviation = actual_rtp - target_rtp
    actual_house_edge = max(0.0, 100.0 - actual_rtp)

    mean_payout = total_payout / num_simulations
    var_payout = sum(count * ((price - mean_payout) ** 2) for count, price in zip(drop_counts, item_prices)) / num_simulations
    se_payout = math.sqrt(var_payout / num_simulations) if num_simulations > 0 else 0.0
    se_rtp = (se_payout / case_price * 100.0) if case_price > 0 else 0.0
    ci_lower = max(0.0, actual_rtp - 1.96 * se_rtp)
    ci_upper = actual_rtp + 1.96 * se_rtp

    expected_counts = [num_simulations * p for p in probs]
    chi2_stat = 0.0
    for obs, exp in zip(drop_counts, expected_counts):
        if exp > 0:
            chi2_stat += ((obs - exp) ** 2) / exp

    df = max(1, k_items - 1)
    p_val = _chi_square_p_value(chi2_stat, df)

    if p_val > 0.05:
        status_text = "🟢 RNG соответствует заданным шансам (p > 0.05)"
        status_level = "green"
    elif p_val > 0.01:
        status_text = "🟡 Небольшое статистическое отклонение (0.01 < p ≤ 0.05)"
        status_level = "yellow"
    else:
        status_text = "🔴 Значительное отклонение от заданной математики (p ≤ 0.01)"
        status_level = "red"

    item_stats = []
    for idx, ci in enumerate(case_items):
        item = ci.item
        obs = drop_counts[idx]
        exp = expected_counts[idx]
        t_chance = probs[idx] * 100.0
        a_chance = (obs / num_simulations) * 100.0
        abs_dev = a_chance - t_chance
        rel_dev = ((a_chance - t_chance) / t_chance * 100.0) if t_chance > 0 else 0.0

        item_stats.append({
            'id': item.id,
            'name': item.name or f"{item.weapon_type} | {item.skin_name}",
            'weapon_type': item.weapon_type,
            'skin_name': item.skin_name,
            'price': float(item.value),
            'rarity': item.rarity,
            'rarity_name': item.get_rarity_display(),
            'rarity_color': item.RARITY_COLORS.get(item.rarity, '#94a3b8'),
            'image_url': item.display_image or '',
            'weight': ci.weight,
            'target_chance': round(t_chance, 4),
            'actual_chance': round(a_chance, 4),
            'drop_count': obs,
            'expected_count': round(exp, 1),
            'abs_deviation': round(abs_dev, 4),
            'rel_deviation': round(rel_dev, 2),
        })

    result = {
        'case_id': case.id,
        'case_name': case.name,
        'case_slug': case.slug,
        'case_price': case_price,
        'num_simulations': num_simulations,
        'total_spent': round(total_spent, 2),
        'total_payout': round(total_payout, 2),
        'target_rtp': round(target_rtp, 2),
        'actual_rtp': round(actual_rtp, 2),
        'deviation': round(deviation, 2),
        'house_edge': round(actual_house_edge, 2),
        'target_house_edge': round(target_house_edge, 2),
        'chi_square_stat': round(chi2_stat, 3),
        'df': df,
        'p_value': round(p_val, 5),
        'status': status_text,
        'status_level': status_level,
        'ci_lower': round(ci_lower, 2),
        'ci_upper': round(ci_upper, 2),
        'server_seed': server_seed,
        'server_seed_hash': hash_seed(server_seed),
        'client_seed': client_seed,
        'items': item_stats,
    }

    if save_run:
        run_record = RngSimulationRun.objects.create(
            case=case,
            user=user if (user and user.is_authenticated) else None,
            num_simulations=num_simulations,
            case_price=Decimal(str(round(case_price, 2))),
            target_rtp=round(target_rtp, 2),
            actual_rtp=round(actual_rtp, 2),
            deviation=round(deviation, 2),
            total_spent=Decimal(str(round(total_spent, 2))),
            total_payout=Decimal(str(round(total_payout, 2))),
            house_edge=round(actual_house_edge, 2),
            chi_square_stat=round(chi2_stat, 3),
            p_value=round(p_val, 5),
            status=status_text,
            status_level=status_level,
            ci_lower=round(ci_lower, 2),
            ci_upper=round(ci_upper, 2),
            server_seed=server_seed,
            client_seed=client_seed,
            item_stats=item_stats,
        )
        result['run_id'] = run_record.id
        result['created_at'] = run_record.created_at.strftime('%d.%m.%Y %H:%M:%S')

    return result
