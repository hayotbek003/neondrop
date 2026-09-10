import os
import re
import json
import zipfile
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from typing import Dict, Any, List, Tuple, Optional, Callable

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.text import slugify

from cases.models import Item


class PubgImportValidationError(Exception):
    """Custom exception raised when ZIP validation fails."""
    pass


def normalize_url(url_str: Optional[str]) -> str:
    """
    Normalizes a URL by trimming whitespace, lowercasing scheme/host,
    and stripping trailing slashes.
    """
    if not url_str:
        return ""
    url_str = str(url_str).strip()
    try:
        parsed = urlparse(url_str)
        if not parsed.netloc and not parsed.path:
            return url_str.rstrip('/')
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip('/')
        return urlunparse((scheme, netloc, path, parsed.params, parsed.query, parsed.fragment))
    except Exception:
        return url_str.rstrip('/')


def map_pubg_rarity(rarity_raw: Optional[str]) -> Tuple[str, str]:
    """
    Maps arbitrary rarity strings (Russian / English / PUBG / CS)
    to the Item model's choice key and HEX color.
    Default fallback is ('rare', '#4B69FF').
    """
    if not rarity_raw:
        return ('rare', '#4B69FF')

    r = str(rarity_raw).strip().lower()

    # Exact matches or keywords
    if any(k in r for k in ['knife', 'нож', 'gold', 'золот']):
        return ('knife', '#FFD700')
    if any(k in r for k in ['mythic', 'мифич', 'ultimate', 'jackpot', 'джекпот']):
        return ('mythic', '#FFD700')
    if any(k in r for k in ['legendary', 'легендар', 'red', 'красн']):
        return ('legendary', '#EB4B4B')
    if any(k in r for k in ['covert', 'тайн']):
        return ('covert', '#EB4B4B')
    if any(k in r for k in ['classified', 'засекреч']):
        return ('classified', '#D32CE6')
    if any(k in r for k in ['epic', 'эпич', 'розов', 'pink', 'magenta']):
        return ('epic', '#D32CE6')
    if any(k in r for k in ['restricted', 'запрещ', 'фиолет', 'purple', 'elite', 'элит']):
        return ('restricted', '#8847FF')
    if any(k in r for k in ['mil_spec', 'армейск']):
        return ('mil_spec', '#4B69FF')
    if any(k in r for k in ['rare', 'редк', 'син', 'blue']):
        return ('rare', '#4B69FF')
    if any(k in r for k in ['industrial', 'промышлен', 'голуб']):
        return ('industrial', '#5E98D9')
    if any(k in r for k in ['uncommon', 'необыч', 'зелен', 'green']):
        return ('uncommon', '#5E98D9')
    if any(k in r for k in ['consumer', 'ширпотреб', 'сер', 'gray', 'grey', 'common', 'обыч', 'classic']):
        return ('common', '#B0C3D9')

    return ('rare', '#4B69FF')


def parse_weapon_and_skin(item_name: str, item_type: str = "") -> Tuple[str, str]:
    """
    Splits an item name into weapon/category and skin name.
    E.g. "M416 | The Fool" -> ("M416", "The Fool")
         "BAPE Camo Hoodie" -> ("Outfit", "BAPE Camo Hoodie")
    """
    name = item_name.strip()
    if ' | ' in name:
        parts = name.split(' | ', 1)
        return parts[0].strip(), parts[1].strip()
    if ' - ' in name:
        parts = name.split(' - ', 1)
        return parts[0].strip(), parts[1].strip()

    t = (item_type or "").strip().capitalize() or "PUBG"
    return t, name


class PubgZipImporter:
    """
    Service to inspect, validate, preview, and atomically import
    PUBG items and their associated image assets from a ZIP file.
    """

    def __init__(self, zip_path: str):
        self.zip_path = Path(zip_path)
        if not self.zip_path.exists():
            raise PubgImportValidationError(f"Файл архива не найден: {zip_path}")
        if not zipfile.is_zipfile(self.zip_path):
            raise PubgImportValidationError("Загруженный файл не является валидным ZIP-архивом.")

    def _get_normalized_namelist(self, zf: zipfile.ZipFile) -> Dict[str, str]:
        """
        Maps normalized path (forward slashes, stripped) to actual name in zip.
        """
        mapping = {}
        for name in zf.namelist():
            norm = name.replace('\\', '/').strip('/')
            mapping[norm] = name
        return mapping

    def _locate_items_json(self, zf: zipfile.ZipFile, norm_map: Dict[str, str]) -> Tuple[str, str]:
        """
        Finds items.json in root or within a single top-level directory.
        Returns (zip_internal_name, relative_prefix).
        """
        if 'items.json' in norm_map:
            return norm_map['items.json'], ''

        # Check subdirectories, ignoring hidden/macOS metadata
        candidates = [k for k in norm_map.keys() if k.endswith('/items.json') and not k.lower().startswith('__macosx')]
        if candidates:
            candidate = candidates[0]
            prefix = candidate[:-len('items.json')]
            return norm_map[candidate], prefix

        raise PubgImportValidationError(
            "В архиве отсутствует файл items.json. Убедитесь, что архив содержит items.json в корне."
        )

    def validate_and_inspect(self) -> Dict[str, Any]:
        """
        Validates the entire ZIP archive without writing to the database:
        - Checks zip integrity (testzip)
        - Finds and parses items.json
        - Checks game == 'PUBG'
        - Checks mandatory fields
        - Verifies that all referenced images physically exist in the zip
        - Matches items against existing DB records

        Returns inspection summary and preview items.
        """
        with zipfile.ZipFile(self.zip_path, 'r') as zf:
            # 1. Zip integrity
            bad_file = zf.testzip()
            if bad_file:
                raise PubgImportValidationError(f"ZIP-архив повреждён (ошибка в файле: {bad_file}).")

            norm_map = self._get_normalized_namelist(zf)
            items_json_name, prefix = self._locate_items_json(zf, norm_map)

            # 2. Read and parse items.json
            try:
                raw_content = zf.read(items_json_name).decode('utf-8')
                data = json.loads(raw_content)
            except UnicodeDecodeError:
                raise PubgImportValidationError("Ошибка кодировки в items.json: файл должен быть в UTF-8.")
            except json.JSONDecodeError as e:
                raise PubgImportValidationError(f"Ошибка синтаксиса в items.json: {e}")

            if not isinstance(data, list):
                raise PubgImportValidationError("items.json должен содержать JSON-массив ([ {...}, {...} ]).")

            if len(data) == 0:
                raise PubgImportValidationError("items.json пуст: массив предметов не содержит записей.")

            # Total image files in zip
            image_extensions = ('.webp', '.png', '.jpg', '.jpeg', '.svg')
            total_images_in_zip = sum(
                1 for name in norm_map.keys()
                if any(name.lower().endswith(ext) for ext in image_extensions)
            )

            preview_items = []
            errors_list = []
            new_count = 0
            existing_count = 0
            error_count = 0

            seen_in_batch_source_ids = set()
            seen_in_batch_urls = set()
            seen_in_batch_names = set()

            for idx, item in enumerate(data, start=1):
                item_errors = []

                if not isinstance(item, dict):
                    item_errors.append("Элемент массива должен быть JSON-объектом.")
                    preview_items.append({
                        'index': idx,
                        'name': f"Item #{idx}",
                        'game': "Unknown",
                        'price': 0,
                        'rarity': "Unknown",
                        'quality': "",
                        'type': "",
                        'image': "",
                        'source_id': "",
                        'source_url': "",
                        'status': 'error',
                        'error_message': "; ".join(item_errors),
                        'matched_by': None,
                    })
                    error_count += 1
                    continue

                # 3. Validate game == PUBG
                game = str(item.get('game', '')).strip()
                if game.upper() != 'PUBG':
                    item_errors.append(f"Игра должна быть строго 'PUBG' (указано: '{game}').")

                # 4. Validate name
                name = str(item.get('name', '')).strip()
                if not name:
                    item_errors.append("Поле 'name' обязательно и не может быть пустым.")

                # 5. Validate price
                price_val = item.get('price')
                if price_val is None:
                    item_errors.append("Поле 'price' обязательно.")
                else:
                    try:
                        price_dec = Decimal(str(price_val))
                        if price_dec < 0:
                            item_errors.append("Цена 'price' не может быть отрицательной.")
                    except (InvalidOperation, TypeError, ValueError):
                        item_errors.append(f"Некорректный формат цены 'price': {price_val}")

                # 6. Validate image presence in zip
                img_path = str(item.get('image', '')).strip().replace('\\', '/').lstrip('/')
                if not img_path:
                    item_errors.append("Поле 'image' обязательно (путь к изображению в архиве).")
                else:
                    # Check direct, prefix-relative, and images/ subfolder variations
                    candidate1 = img_path
                    candidate2 = f"{prefix}{img_path}" if prefix else img_path
                    alt_path = f"images/{img_path}" if not img_path.startswith('images/') else img_path[7:]
                    candidate3 = alt_path
                    candidate4 = f"{prefix}{alt_path}" if prefix else alt_path
                    if (candidate1 not in norm_map and candidate2 not in norm_map and
                        candidate3 not in norm_map and candidate4 not in norm_map):
                        item_errors.append(f"Изображение '{img_path}' не найдено внутри ZIP-архива.")

                # If there are structural errors for this item
                if item_errors:
                    error_count += 1
                    err_msg = "; ".join(item_errors)
                    errors_list.append(f"Предмет #{idx} ({name or 'без имени'}): {err_msg}")
                    preview_items.append({
                        'index': idx,
                        'name': name or f"Предмет #{idx}",
                        'game': game,
                        'price': float(price_dec) if 'price_dec' in locals() and price_dec >= 0 else 0,
                        'rarity': item.get('rarity', ''),
                        'quality': item.get('quality', ''),
                        'type': item.get('type', 'skin'),
                        'image': img_path,
                        'source_id': item.get('source_id', ''),
                        'source_url': item.get('source_url', ''),
                        'status': 'error',
                        'error_message': err_msg,
                        'matched_by': None,
                    })
                    continue

                # 7. Check if item already exists in NEONDROP DB
                existing_item, match_type, match_explanation = self.find_existing_item(item)

                raw_source_id = item.get('source_id')
                if raw_source_id is None and 'source_id' not in item:
                    raw_source_id = item.get('id')
                source_id = str(raw_source_id).strip() if raw_source_id is not None and str(raw_source_id).strip() else None

                raw_source_url = item.get('source_url')
                source_url_norm = normalize_url(str(raw_source_url).strip()) if raw_source_url is not None and str(raw_source_url).strip() else None

                norm_name = " ".join(str(name).strip().split())
                norm_game = " ".join(str(game).strip().split())

                # Batch duplicate detection within this ZIP archive using the exact same hierarchy
                is_batch_duplicate = False
                batch_dup_reason = None
                if source_id:
                    if source_id in seen_in_batch_source_ids:
                        is_batch_duplicate = True
                        batch_dup_reason = 'Дубликат в архиве (по source_id)'
                    seen_in_batch_source_ids.add(source_id)
                elif source_url_norm:
                    if source_url_norm in seen_in_batch_urls:
                        is_batch_duplicate = True
                        batch_dup_reason = 'Дубликат в архиве (по source_url)'
                    seen_in_batch_urls.add(source_url_norm)
                elif norm_name:
                    name_key = (norm_game.lower(), norm_name.lower())
                    if name_key in seen_in_batch_names:
                        is_batch_duplicate = True
                        batch_dup_reason = 'Дубликат в архиве (по game + name)'
                    seen_in_batch_names.add(name_key)

                # An item is EXISTING if and only if it was found in the database.
                # If not found in DB, it is strictly NEW!
                if existing_item:
                    existing_count += 1
                    status = 'exists'
                    display_status = 'EXISTING'
                else:
                    new_count += 1
                    status = 'new'
                    display_status = 'NEW'

                rarity_code, rarity_hex = map_pubg_rarity(item.get('rarity'))

                preview_items.append({
                    'index': idx,
                    'name': name,
                    'game': game,
                    'price': float(price_dec),
                    'rarity': item.get('rarity', ''),
                    'rarity_code': rarity_code,
                    'rarity_hex': rarity_hex,
                    'quality': item.get('quality', ''),
                    'type': item.get('type', 'skin'),
                    'image': img_path,
                    'source_id': source_id or '',
                    'source_url': item.get('source_url', '') or '',
                    'source_image_url': item.get('source_image_url', '') or '',
                    'status': status,
                    'display_status': display_status,
                    'existing_id': existing_item.id if existing_item else None,
                    'matched_by': match_type,
                    'match_explanation': match_explanation,
                    'is_batch_duplicate': is_batch_duplicate,
                    'batch_dup_reason': batch_dup_reason,
                    'error_message': None,
                })

            is_valid = (error_count == 0)

            return {
                'is_valid': is_valid,
                'total_items': len(data),
                'new_items': new_count,
                'existing_items': existing_count,
                'error_items': error_count,
                'total_images': total_images_in_zip,
                'errors_list': errors_list,
                'preview_items': preview_items,
            }

    # Alias for convenience
    inspect_and_validate = validate_and_inspect

    @staticmethod
    def find_existing_item(item_data: Dict[str, Any]) -> Tuple[Optional[Item], Optional[str], Optional[str]]:
        """
        Strictly determines if an item already exists in NEONDROP.
        Priority hierarchy (strictly exclusive, no fuzzy matching):
        1. If source_id is present in imported item (non-empty string or integer):
           Search existing Item by source_id ONLY.
           If found -> return (item, 'source_id', 'Совпало по source_id')
           If NOT found -> return (None, None, None) [Strictly NEW, no fallback!]

        2. If source_id is absent, but source_url is present (non-empty):
           Search existing Item by normalized source_url ONLY.
           If found -> return (item, 'source_url', 'Совпало по source_url')
           If NOT found -> return (None, None, None) [Strictly NEW, no fallback!]

        3. If both source_id and source_url are absent:
           Search existing Item by strict exact match: game + normalized full name.
           No fuzzy matching.
           If found -> return (item, 'name_game', 'Совпало по game + name')
           If NOT found -> return (None, None, None) [Strictly NEW]
        """
        # Step 1: source_id check
        raw_source_id = item_data.get('source_id')
        if raw_source_id is None and 'source_id' not in item_data:
            raw_source_id = item_data.get('id')

        source_id = str(raw_source_id).strip() if raw_source_id is not None and str(raw_source_id).strip() else None

        if source_id:
            existing = Item.objects.exclude(source_id__isnull=True).exclude(source_id='').filter(source_id=source_id).first()
            if existing:
                return existing, 'source_id', 'Совпало по source_id'
            # Has source_id, but no matching source_id in DB -> MUST be NEW!
            return None, None, None

        # Step 2: source_url check (only when source_id is absent)
        raw_source_url = item_data.get('source_url')
        source_url = str(raw_source_url).strip() if raw_source_url is not None and str(raw_source_url).strip() else None

        if source_url:
            norm_url = normalize_url(source_url)
            if norm_url:
                existing = Item.objects.exclude(source_url__isnull=True).exclude(source_url='').filter(source_url=norm_url).first()
                if not existing:
                    alt_url = norm_url.rstrip('/') if norm_url.endswith('/') else norm_url + '/'
                    existing = Item.objects.exclude(source_url__isnull=True).exclude(source_url='').filter(source_url=alt_url).first()
                if existing:
                    return existing, 'source_url', 'Совпало по source_url'
            # Has source_url, but no matching source_url in DB -> MUST be NEW!
            return None, None, None

        # Step 3: Strict exact match by game + full normalized name
        raw_name = item_data.get('name')
        norm_name = " ".join(str(raw_name).strip().split()) if raw_name is not None and str(raw_name).strip() else ""
        raw_game = item_data.get('game') or 'PUBG'
        norm_game = " ".join(str(raw_game).strip().split())

        if norm_name:
            # Query exact match (case-insensitive on name, exact on game)
            existing = Item.objects.filter(name__iexact=norm_name, game__iexact=norm_game).first()
            if existing:
                # Extra guard: verify that collapsed normalized string matches exactly
                existing_norm_name = " ".join(existing.name.strip().split())
                if existing_norm_name.lower() == norm_name.lower():
                    return existing, 'name_game', 'Совпало по game + name'

        return None, None, None

    def execute_import(
        self,
        mode: str = 'add_only',
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes the import atomically inside a database transaction:
        - mode: 'add_only' or 'update_existing'
        - Calls progress_callback(current, total, item_name)
        - Prevents partial imports if validation fails
        - Saves images to media/items/ and attaches to Item.image
        - Returns full summary
        """
        # Step 1: Pre-validation of entire ZIP
        inspection = self.validate_and_inspect()
        if not inspection['is_valid']:
            first_errors = "; ".join(inspection['errors_list'][:5])
            raise PubgImportValidationError(
                f"Валидация ZIP-архива не пройдена ({inspection['error_items']} ошибок). "
                f"Импорт отменён. Примеры ошибок: {first_errors}"
            )

        items_to_process = inspection['preview_items']
        total_items = len(items_to_process)

        created_count = 0
        updated_count = 0
        skipped_count = 0
        images_saved_count = 0
        error_count = 0

        # Cache of items created/updated during this run to prevent duplicate inserts from same ZIP
        processed_source_ids = set()
        processed_urls = set()
        processed_names = set()

        with zipfile.ZipFile(self.zip_path, 'r') as zf:
            norm_map = self._get_normalized_namelist(zf)
            _, prefix = self._locate_items_json(zf, norm_map)

            # Helper to read image bytes from zip
            def get_image_bytes_and_ext(img_path: str) -> Tuple[bytes, str]:
                clean_path = img_path.replace('\\', '/').lstrip('/')
                alt_path = f"images/{clean_path}" if not clean_path.startswith('images/') else clean_path[7:]
                actual_zip_name = (
                    norm_map.get(clean_path)
                    or norm_map.get(f"{prefix}{clean_path}")
                    or norm_map.get(alt_path)
                    or norm_map.get(f"{prefix}{alt_path}")
                )
                if not actual_zip_name:
                    raise FileNotFoundError(f"Изображение '{img_path}' отсутствует в архиве.")
                ext = Path(actual_zip_name).suffix or '.webp'
                return zf.read(actual_zip_name), ext

            # Atomic database transaction: all or nothing
            with transaction.atomic():
                for idx, p_item in enumerate(items_to_process, start=1):
                    item_name = p_item['name']
                    if progress_callback:
                        progress_callback(idx, total_items, item_name)

                    # Find existing item using strict 3-step hierarchy
                    existing_item, match_type, _ = self.find_existing_item(p_item)

                    raw_source_id = p_item.get('source_id')
                    if raw_source_id is None and 'source_id' not in p_item:
                        raw_source_id = p_item.get('id')
                    source_id = str(raw_source_id).strip() if raw_source_id is not None and str(raw_source_id).strip() else None

                    raw_source_url = p_item.get('source_url')
                    source_url_norm = normalize_url(str(raw_source_url).strip()) if raw_source_url is not None and str(raw_source_url).strip() else None

                    norm_name = " ".join(str(item_name).strip().split())
                    norm_game = " ".join(str(p_item.get('game') or 'PUBG').strip().split())
                    name_key = (norm_game.lower(), norm_name.lower())

                    # Batch deduplication in execute_import following exact hierarchy
                    if source_id:
                        if source_id in processed_source_ids:
                            skipped_count += 1
                            continue
                    elif source_url_norm:
                        if source_url_norm in processed_urls:
                            skipped_count += 1
                            continue
                    elif norm_name:
                        if name_key in processed_names:
                            skipped_count += 1
                            continue

                    # MODE: ADD ONLY
                    if mode == 'add_only':
                        if existing_item:
                            skipped_count += 1
                            if source_id:
                                processed_source_ids.add(source_id)
                            elif source_url_norm:
                                processed_urls.add(source_url_norm)
                            elif norm_name:
                                processed_names.add(name_key)
                            continue

                        # Create new Item
                        img_bytes, ext = get_image_bytes_and_ext(p_item['image'])
                        weapon_type, skin_name = parse_weapon_and_skin(item_name, p_item.get('type', ''))
                        rarity_code, rarity_hex = map_pubg_rarity(p_item.get('rarity'))

                        new_item = Item(
                            name=item_name,
                            weapon_type=weapon_type,
                            skin_name=skin_name,
                            value=Decimal(str(p_item['price'])),
                            rarity=rarity_code,
                            rarity_color=rarity_hex,
                            game='PUBG',
                            quality=p_item.get('quality', ''),
                            item_type=p_item.get('type', 'skin'),
                            source_id=source_id or None,
                            source_url=source_url_norm or None,
                            source_image_url=p_item.get('source_image_url') or None,
                        )

                        # Save image to Item.image
                        safe_slug = slugify(item_name)[:40] or f"item_{idx}"
                        filename = f"pubg_{safe_slug}_{idx}{ext}"
                        new_item.image.save(filename, ContentFile(img_bytes), save=False)
                        new_item.save()

                        created_count += 1
                        images_saved_count += 1

                        if source_id:
                            processed_source_ids.add(source_id)
                        if source_url_norm:
                            processed_urls.add(source_url_norm)
                        processed_names.add(name_key)

                    # MODE: UPDATE EXISTING
                    elif mode == 'update_existing':
                        if existing_item:
                            # Update existing item fields
                            weapon_type, skin_name = parse_weapon_and_skin(item_name, p_item.get('type', ''))
                            rarity_code, rarity_hex = map_pubg_rarity(p_item.get('rarity'))

                            existing_item.name = item_name
                            existing_item.weapon_type = weapon_type
                            existing_item.skin_name = skin_name
                            existing_item.value = Decimal(str(p_item['price']))
                            existing_item.rarity = rarity_code
                            existing_item.rarity_color = rarity_hex
                            existing_item.quality = p_item.get('quality', '') or ""
                            existing_item.item_type = p_item.get('type', 'skin') or "skin"
                            if source_id:
                                existing_item.source_id = source_id
                            if source_url_norm:
                                existing_item.source_url = source_url_norm
                            if p_item.get('source_image_url'):
                                existing_item.source_image_url = p_item['source_image_url']

                            # Update image if provided and exists
                            try:
                                img_bytes, ext = get_image_bytes_and_ext(p_item['image'])
                                safe_slug = slugify(item_name)[:40] or f"item_{existing_item.id}"
                                filename = f"pubg_{safe_slug}_{existing_item.id}{ext}"
                                existing_item.image.save(filename, ContentFile(img_bytes), save=False)
                                images_saved_count += 1
                            except Exception:
                                pass

                            existing_item.save()
                            updated_count += 1

                            if source_id:
                                processed_source_ids.add(source_id)
                            if source_url_norm:
                                processed_urls.add(source_url_norm)
                            processed_names.add(name_key)
                        else:
                            # Item doesn't exist, create it
                            img_bytes, ext = get_image_bytes_and_ext(p_item['image'])
                            weapon_type, skin_name = parse_weapon_and_skin(item_name, p_item.get('type', ''))
                            rarity_code, rarity_hex = map_pubg_rarity(p_item.get('rarity'))

                            new_item = Item(
                                name=item_name,
                                weapon_type=weapon_type,
                                skin_name=skin_name,
                                value=Decimal(str(p_item['price'])),
                                rarity=rarity_code,
                                rarity_color=rarity_hex,
                                game='PUBG',
                                quality=p_item.get('quality', ''),
                                item_type=p_item.get('type', 'skin'),
                                source_id=source_id or None,
                                source_url=source_url_norm or None,
                                source_image_url=p_item.get('source_image_url') or None,
                            )

                            safe_slug = slugify(item_name)[:40] or f"item_{idx}"
                            filename = f"pubg_{safe_slug}_{idx}{ext}"
                            new_item.image.save(filename, ContentFile(img_bytes), save=False)
                            new_item.save()

                            created_count += 1
                            images_saved_count += 1

                            if source_id:
                                processed_source_ids.add(source_id)
                            if source_url_norm:
                                processed_urls.add(source_url_norm)
                            processed_names.add(name_key)

        return {
            'success': True,
            'total': total_items,
            'created': created_count,
            'updated': updated_count,
            'skipped': skipped_count,
            'errors': error_count,
            'images_saved': images_saved_count,
        }
