import hashlib
import hmac
import secrets
from typing import List, Tuple, Any

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

def select_weighted_item(case_items: List[Any], server_seed: str, client_seed: str, nonce: int):
    """
    Select an item from case_items based on their weights using provably fair roll.
    Returns: (selected_case_item, roll_float, server_seed_hash)
    """
    server_seed_hash = hash_seed(server_seed)
    roll = calculate_provably_fair_roll(server_seed, client_seed, nonce)
    
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
