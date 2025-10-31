"""Utility helper functions for deck builder.

This module houses pure/stateless helper logic that was previously embedded
inside the large builder.py module. Extracting them here keeps the DeckBuilder
class leaner and makes the logic easier to test independently.

Only import lightweight standard library modules here to avoid import cycles.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List
import re
import ast
import random as _rand
from functools import lru_cache
from pathlib import Path

import pandas as pd

from . import builder_constants as bc
import math
from path_util import csv_dir

COLOR_LETTERS = ['W', 'U', 'B', 'R', 'G']
_MULTI_FACE_LAYOUTS = {
	"adventure",
	"aftermath",
	"augment",
	"flip",
	"host",
	"meld",
	"modal_dfc",
	"reversible_card",
	"split",
	"transform",
}
_SIDE_PRIORITY = {
	"": 0,
	"a": 0,
	"front": 0,
	"main": 0,
	"b": 1,
	"back": 1,
	"c": 2,
}


def _detect_produces_mana(text: str) -> bool:
	text = (text or "").lower()
	if not text:
		return False
	if 'add one mana of any color' in text or 'add one mana of any colour' in text:
		return True
	if 'add mana of any color' in text or 'add mana of any colour' in text:
		return True
	if 'mana of any one color' in text or 'any color of mana' in text:
		return True
	if 'add' in text:
		for sym in ('{w}', '{u}', '{b}', '{r}', '{g}', '{c}'):
			if sym in text:
				return True
	return False


def _extract_colors_from_land_type(type_line: str) -> List[str]:
	"""Extract mana colors from basic land types in a type line.
	
	Args:
		type_line: Card type line (e.g., "Land — Mountain", "Land — Forest Plains")
		
	Returns:
		List of color letters (e.g., ['R'], ['G', 'W'])
	"""
	if not isinstance(type_line, str):
		return []
	type_lower = type_line.lower()
	colors = []
	basic_land_colors = {
		'plains': 'W',
		'island': 'U',
		'swamp': 'B',
		'mountain': 'R',
		'forest': 'G',
	}
	for land_type, color in basic_land_colors.items():
		if land_type in type_lower:
			colors.append(color)
	return colors


def _resolved_csv_dir(base_dir: str | None = None) -> str:
	try:
		if base_dir:
			return str(Path(base_dir).resolve())
		return str(Path(csv_dir()).resolve())
	except Exception:
		return base_dir or csv_dir()


# M7: Cache for all cards Parquet DataFrame to avoid repeated loads
_ALL_CARDS_CACHE: Dict[str, Any] = {"df": None, "mtime": None}


def _load_all_cards_parquet() -> pd.DataFrame:
	"""Load all cards from the unified Parquet file with caching.
	
	M4: Centralized Parquet loading for deck builder.
	M7: Added module-level caching to avoid repeated file loads.
	Returns empty DataFrame on error (defensive).
	Converts numpy arrays to Python lists for compatibility with existing code.
	"""
	global _ALL_CARDS_CACHE
	
	try:
		from code.path_util import get_processed_cards_path
		from code.file_setup.data_loader import DataLoader
		import numpy as np
		import os
		
		parquet_path = get_processed_cards_path()
		if not Path(parquet_path).exists():
			return pd.DataFrame()
		
		# M7: Check cache and mtime
		need_reload = _ALL_CARDS_CACHE["df"] is None
		if not need_reload:
			try:
				current_mtime = os.path.getmtime(parquet_path)
				cached_mtime = _ALL_CARDS_CACHE.get("mtime")
				if cached_mtime is None or current_mtime > cached_mtime:
					need_reload = True
			except Exception:
				# If mtime check fails, use cached version if available
				pass
		
		if need_reload:
			data_loader = DataLoader()
			df = data_loader.read_cards(parquet_path, format="parquet")
			
			# M4: Convert numpy arrays to Python lists for compatibility
			# Parquet stores lists as numpy arrays, but existing code expects Python lists
			list_columns = ['themeTags', 'creatureTypes', 'metadataTags', 'keywords']
			for col in list_columns:
				if col in df.columns:
					df[col] = df[col].apply(lambda x: x.tolist() if isinstance(x, np.ndarray) else x)
			
			# M7: Cache the result
			_ALL_CARDS_CACHE["df"] = df
			try:
				_ALL_CARDS_CACHE["mtime"] = os.path.getmtime(parquet_path)
			except Exception:
				_ALL_CARDS_CACHE["mtime"] = None
		
		return _ALL_CARDS_CACHE["df"]
	except Exception:
		return pd.DataFrame()


@lru_cache(maxsize=None)
def _load_multi_face_land_map(base_dir: str) -> Dict[str, Dict[str, Any]]:
	"""Load mapping of multi-faced cards that have at least one land face.
	
	M4: Migrated to use Parquet loading. base_dir parameter kept for
	backward compatibility but now only used as cache key.
	"""
	try:
		# M4: Load from Parquet instead of CSV
		df = _load_all_cards_parquet()
		if df.empty:
			return {}
		
		# Select only needed columns
		# M9: Added backType to detect MDFC lands where land is on back face
		# M9: Added colorIdentity to extract mana colors for MDFC lands
		usecols = ['name', 'layout', 'side', 'type', 'text', 'manaCost', 'manaValue', 'faceName', 'backType', 'colorIdentity']
		available_cols = [col for col in usecols if col in df.columns]
		if not available_cols:
			return {}
		df = df[available_cols].copy()
	except Exception:
		return {}
	if df.empty or 'layout' not in df.columns or 'type' not in df.columns:
		return {}
	df['layout'] = df['layout'].fillna('').astype(str).str.lower()
	multi_df = df[df['layout'].isin(_MULTI_FACE_LAYOUTS)].copy()
	if multi_df.empty:
		return {}
	multi_df['type'] = multi_df['type'].fillna('').astype(str)
	multi_df['side'] = multi_df['side'].fillna('').astype(str)
	multi_df['text'] = multi_df['text'].fillna('').astype(str)
	# M9: Check both type and backType for land faces
	if 'backType' in multi_df.columns:
		multi_df['backType'] = multi_df['backType'].fillna('').astype(str)
		land_mask = (
			multi_df['type'].str.contains('land', case=False, na=False) |
			multi_df['backType'].str.contains('land', case=False, na=False)
		)
		land_rows = multi_df[land_mask]
	else:
		land_rows = multi_df[multi_df['type'].str.contains('land', case=False, na=False)]
	if land_rows.empty:
		return {}
	mapping: Dict[str, Dict[str, Any]] = {}
	for name, group in land_rows.groupby('name', sort=False):
		faces: List[Dict[str, str]] = []
		seen: set[tuple[str, str, str]] = set()
		front_is_land = False
		layout_val = ''
		
		# M9: Handle merged rows with backType
		if len(group) == 1 and 'backType' in group.columns:
			row = group.iloc[0]
			back_type_val = str(row.get('backType', '') or '')
			if back_type_val and 'land' in back_type_val.lower():
				# Construct synthetic faces from merged row
				front_type = str(row.get('type', '') or '')
				front_text = str(row.get('text', '') or '')
				mana_cost_val = str(row.get('manaCost', '') or '')
				mana_value_raw = row.get('manaValue', '')
				mana_value_val = None
				try:
					if mana_value_raw not in (None, ''):
						mana_value_val = float(mana_value_raw)
						if math.isnan(mana_value_val):
							mana_value_val = None
				except Exception:
					mana_value_val = None
				
				# Front face
				faces.append({
					'face': str(row.get('faceName', '') or name),
					'side': 'a',
					'type': front_type,
					'text': front_text,
					'mana_cost': mana_cost_val,
					'mana_value': mana_value_val,
					'produces_mana': _detect_produces_mana(front_text),
					'is_land': 'land' in front_type.lower(),
					'layout': str(row.get('layout', '') or ''),
				})
				
				# Back face (synthesized)
				# M9: Use colorIdentity column for MDFC land colors (more reliable than parsing type line)
				color_identity_raw = row.get('colorIdentity', [])
				if isinstance(color_identity_raw, str):
					# Handle string format like "['G']" or "G"
					try:
						import ast
						color_identity_raw = ast.literal_eval(color_identity_raw)
					except Exception:
						color_identity_raw = [c.strip() for c in color_identity_raw.split(',') if c.strip()]
				back_face_colors = list(color_identity_raw) if color_identity_raw else []
				# Fallback to parsing land type if colorIdentity not available
				if not back_face_colors:
					back_face_colors = _extract_colors_from_land_type(back_type_val)
				
				faces.append({
					'face': name.split(' // ')[1] if ' // ' in name else 'Back',
					'side': 'b',
					'type': back_type_val,
					'text': '',  # Not available in merged row
					'mana_cost': '',
					'mana_value': None,
					'produces_mana': True,  # Assume land produces mana
					'is_land': True,
					'layout': str(row.get('layout', '') or ''),
					'colors': back_face_colors,  # M9: Color information for mana sources
				})
				
				front_is_land = 'land' in front_type.lower()
				layout_val = str(row.get('layout', '') or '')
				mapping[name] = {
					'faces': faces,
					'front_is_land': front_is_land,
					'layout': layout_val,
					'colors': back_face_colors,  # M9: Store colors at top level for easy access
				}
				continue
		
		# Original logic for multi-row format
		for _, row in group.iterrows():
			side_raw = str(row.get('side', '') or '').strip()
			side_key = side_raw.lower()
			if not side_key:
				side_key = 'a'
			type_val = str(row.get('type', '') or '')
			text_val = str(row.get('text', '') or '')
			mana_cost_val = str(row.get('manaCost', '') or '')
			mana_value_raw = row.get('manaValue', '')
			mana_value_val = None
			try:
				if mana_value_raw not in (None, ''):
					mana_value_val = float(mana_value_raw)
					if math.isnan(mana_value_val):
						mana_value_val = None
			except Exception:
				mana_value_val = None
			face_label = str(row.get('faceName', '') or row.get('name', '') or '')
			produces_mana = _detect_produces_mana(text_val)
			signature = (side_key, type_val, text_val)
			if signature in seen:
				continue
			seen.add(signature)
			faces.append({
				'face': face_label,
				'side': side_key,
				'type': type_val,
				'text': text_val,
				'mana_cost': mana_cost_val,
				'mana_value': mana_value_val,
				'produces_mana': produces_mana,
				'is_land': 'land' in type_val.lower(),
				'layout': str(row.get('layout', '') or ''),
			})
			if side_key in ('', 'a', 'front', 'main'):
				front_is_land = True
			layout_val = layout_val or str(row.get('layout', '') or '')
		if not faces:
			continue
		faces.sort(key=lambda face: _SIDE_PRIORITY.get(face.get('side', ''), 3))
		mapping[name] = {
			'faces': faces,
			'front_is_land': front_is_land,
			'layout': layout_val,
		}
	return mapping


def multi_face_land_info(name: str, base_dir: str | None = None) -> Dict[str, Any]:
	return _load_multi_face_land_map(_resolved_csv_dir(base_dir)).get(name, {})


def get_multi_face_land_faces(name: str, base_dir: str | None = None) -> List[Dict[str, str]]:
	entry = multi_face_land_info(name, base_dir)
	return list(entry.get('faces', []))


def has_multi_face_land(name: str, base_dir: str | None = None) -> bool:
	entry = multi_face_land_info(name, base_dir)
	return bool(entry and entry.get('faces'))


def parse_theme_tags(val) -> list[str]:
	"""Robustly parse a themeTags cell that may be a list, nested list, or string-repr.

	Handles formats like:
	  ['Tag1', 'Tag2']
	  "['Tag1', 'Tag2']"
	  Tag1, Tag2
	  numpy.ndarray (from Parquet)
	Returns list of stripped string tags (may be empty)."""
	# M4: Handle numpy arrays from Parquet
	import numpy as np
	if isinstance(val, np.ndarray):
		return [str(x).strip() for x in val.tolist() if x and str(x).strip()]
	
	if isinstance(val, list):
		flat: list[str] = []
		for v in val:
			if isinstance(v, list):
				flat.extend(str(x) for x in v)
			else:
				flat.append(str(v))
		return [s.strip() for s in flat if s and str(s).strip()]
	if isinstance(val, str):
		s = val.strip()
		# Try literal list first
		try:
			parsed = ast.literal_eval(s)
			if isinstance(parsed, list):
				return [str(x).strip() for x in parsed if str(x).strip()]
		except Exception:
			pass
		# Fallback comma split
		if s.startswith('[') and s.endswith(']'):
			s = s[1:-1]
		parts = [p.strip().strip("'\"") for p in s.split(',')]
		out: list[str] = []
		for p in parts:
			if not p:
				continue
			clean = re.sub(r"^[\[\s']+|[\]\s']+$", '', p)
			if clean:
				out.append(clean)
		return out
	return []


def ensure_theme_tags_list(val) -> list[str]:
	"""Safely convert themeTags value to list, handling None, lists, and numpy arrays.
	
	This is a simpler wrapper around parse_theme_tags for the common case where
	you just need to ensure you have a list to work with.
	"""
	if val is None:
		return []
	return parse_theme_tags(val)



def normalize_theme_list(raw) -> list[str]:
	"""Parse then lowercase + strip each tag."""
	tags = parse_theme_tags(raw)
	return [t.lower().strip() for t in tags if t and t.strip()]


def compute_color_source_matrix(card_library: Dict[str, dict], full_df) -> Dict[str, Dict[str, int]]:
	"""Build a matrix mapping card name -> {color: 0/1} indicating if that card
	can (reliably) produce each color of mana on the battlefield.

	Notes:
	  - Includes lands and non-lands (artifacts/creatures/enchantments/planeswalkers) that produce mana.
	  - Excludes instants/sorceries (rituals) by design; this is a "source" count, not ramp burst.
	  - Any-color effects set W/U/B/R/G (not C). Colorless '{C}' is tracked separately.
	  - For lands, we also infer from basic land types in the type line. For non-lands, we rely on text.
	  - Fallback name mapping applies only to exact basic lands (incl. Snow-Covered) and Wastes.

	Parameters
	----------
	card_library : Dict[str, dict]
		Current deck card entries (expects 'Card Type' and 'Count').
	full_df : pandas.DataFrame | None
		Full card dataset used for type/text lookups. May be None/empty.
	"""
	matrix: Dict[str, Dict[str, int]] = {}
	lookup = {}
	if full_df is not None and not getattr(full_df, 'empty', True) and 'name' in full_df.columns:
		for _, r in full_df.iterrows():
			nm = str(r.get('name', ''))
			if nm and nm not in lookup:
				lookup[nm] = r
	try:
		dfc_map = _load_multi_face_land_map(_resolved_csv_dir())
	except Exception:
		dfc_map = {}
	for name, entry in card_library.items():
		row = lookup.get(name, {})
		entry_type_raw = str(entry.get('Card Type') or entry.get('Type') or '')
		entry_type = entry_type_raw.lower()
		row_type_raw = ''
		if hasattr(row, 'get'):
			row_type_raw = row.get('type', row.get('type_line', '')) or ''
		tline_full = str(row_type_raw).lower()
		# M9: Check backType for MDFC land detection
		back_type_raw = ''
		if hasattr(row, 'get'):
			back_type_raw = row.get('backType', '') or ''
		back_type = str(back_type_raw).lower()
		# Land or permanent that could produce mana via text
		is_land = ('land' in entry_type) or ('land' in tline_full) or ('land' in back_type)
		base_is_land = is_land
		text_field_raw = ''
		if hasattr(row, 'get'):
			text_field_raw = row.get('text', row.get('oracleText', '')) or ''
		if pd.isna(text_field_raw):
			text_field_raw = ''
		text_field_raw = str(text_field_raw)
		dfc_entry = dfc_map.get(name)
		if dfc_entry:
			faces = dfc_entry.get('faces', []) or []
			if faces:
				face_types: List[str] = []
				face_texts: List[str] = []
				for face in faces:
					type_val = str(face.get('type', '') or '')
					text_val = str(face.get('text', '') or '')
					if type_val:
						face_types.append(type_val)
					if text_val:
						face_texts.append(text_val)
				if face_types:
					joined_types = ' '.join(face_types)
					tline_full = (tline_full + ' ' + joined_types.lower()).strip()
				if face_texts:
					joined_text = ' '.join(face_texts)
					text_field_raw = (text_field_raw + ' ' + joined_text).strip()
				if face_types or face_texts:
					is_land = True
		text_field = text_field_raw.lower().replace('\n', ' ')
		# Skip obvious non-permanents (rituals etc.) - but NOT if any face is a land
		# M9: If is_land is True (from backType check), we keep it regardless of front face type
		if (not is_land) and ('instant' in entry_type or 'sorcery' in entry_type or 'instant' in tline_full or 'sorcery' in tline_full):
			continue
		# Keep only candidates that are lands OR whose text indicates mana production
		produces_from_text = False
		tf = text_field
		if tf:
			# Common patterns: "Add {G}", "Add {C}{C}", "Add one mana of any color/colour"
			produces_from_text = (
				('add one mana of any color' in tf) or
				('add one mana of any colour' in tf) or
				('add ' in tf and ('{w}' in tf or '{u}' in tf or '{b}' in tf or '{r}' in tf or '{g}' in tf or '{c}' in tf))
			)
		if not (is_land or produces_from_text):
			continue
		# Combine entry type and snapshot type line for robust parsing
		tline = (entry_type + ' ' + tline_full).strip()
		colors = {c: 0 for c in (COLOR_LETTERS + ['C'])}
		# Land type-based inference
		if is_land:
			if 'plains' in tline:
				colors['W'] = 1
			if 'island' in tline:
				colors['U'] = 1
			if 'swamp' in tline:
				colors['B'] = 1
			if 'mountain' in tline:
				colors['R'] = 1
			if 'forest' in tline:
				colors['G'] = 1
		# Text-based inference for both lands and non-lands
		if (
			'add one mana of any color' in tf or
			'add one mana of any colour' in tf or
			('add' in tf and ('mana of any color' in tf or 'mana of any one color' in tf or 'any color of mana' in tf))
		):
			for k in COLOR_LETTERS:
				colors[k] = 1
		# Explicit colored/colorless symbols in add context
		if 'add' in tf:
			if '{w}' in tf:
				colors['W'] = 1
			if '{u}' in tf:
				colors['U'] = 1
			if '{b}' in tf:
				colors['B'] = 1
			if '{r}' in tf:
				colors['R'] = 1
			if '{g}' in tf:
				colors['G'] = 1
			if '{c}' in tf or 'colorless' in tf:
				colors['C'] = 1
		# Fallback: infer only for exact basic land names (incl. Snow-Covered) and Wastes
		if not any(colors.values()) and is_land:
			nm = str(name)
			base = nm
			if nm.startswith('Snow-Covered '):
				base = nm[len('Snow-Covered '):]
			mapping = {
				'Plains': 'W',
				'Island': 'U',
				'Swamp': 'B',
				'Mountain': 'R',
				'Forest': 'G',
				'Wastes': 'C',
			}
			col = mapping.get(base)
			if col:
				colors[col] = 1
		dfc_is_land = bool(dfc_entry and dfc_entry.get('faces'))
		if dfc_is_land:
			colors['_dfc_land'] = True
			if not (base_is_land or dfc_entry.get('front_is_land')):
				colors['_dfc_counts_as_extra'] = True
			# M9: Extract colors from DFC face metadata (back face land colors)
			dfc_colors = dfc_entry.get('colors', [])
			if dfc_colors:
				for color in dfc_colors:
					if color in colors:
						colors[color] = 1
		produces_any_color = any(colors[c] for c in ('W', 'U', 'B', 'R', 'G', 'C'))
		if produces_any_color or colors.get('_dfc_land'):
			matrix[name] = colors
	return matrix


def compute_spell_pip_weights(card_library: Dict[str, dict], color_identity: Iterable[str]) -> Dict[str, float]:
	"""Compute relative colored mana pip weights from non-land spells.

	Hybrid symbols are split evenly among their component colors. If no colored
	pips are found we fall back to an even distribution across the commander's
	color identity (or 0s if identity empty).
	"""
	pip_counts = {c: 0 for c in COLOR_LETTERS}
	total_colored = 0.0
	for entry in card_library.values():
		ctype = str(entry.get('Card Type', ''))
		if 'land' in ctype.lower():
			continue
		mana_cost = entry.get('Mana Cost') or entry.get('mana_cost') or ''
		if not isinstance(mana_cost, str):
			continue
		for match in re.findall(r'\{([^}]+)\}', mana_cost):
			sym = match.upper()
			if len(sym) == 1 and sym in pip_counts:
				pip_counts[sym] += 1
				total_colored += 1
			else:
				if '/' in sym:
					parts = [p for p in sym.split('/') if p in pip_counts]
					if parts:
						weight_each = 1 / len(parts)
						for p in parts:
							pip_counts[p] += weight_each
							total_colored += weight_each
	if total_colored <= 0:
		colors = [c for c in color_identity if c in pip_counts]
		if not colors:
			return {c: 0.0 for c in pip_counts}
		share = 1 / len(colors)
		return {c: (share if c in colors else 0.0) for c in pip_counts}
	return {c: (pip_counts[c] / total_colored) for c in pip_counts}



__all__ = [
	'compute_color_source_matrix',
	'compute_spell_pip_weights',
	'parse_theme_tags',
	'normalize_theme_list',
	'multi_face_land_info',
	'get_multi_face_land_faces',
	'has_multi_face_land',
	'detect_viable_multi_copy_archetypes',
	'prefer_owned_first',
	'compute_adjusted_target',
	'normalize_tag_cell',
	'sort_by_priority',
	'COLOR_LETTERS',
	'tapped_land_penalty',
	'replacement_land_score',
	'build_tag_driven_suggestions',
	'select_color_balance_removal',
	'color_balance_addition_candidates',
	'basic_land_names',
	'count_basic_lands',
	'choose_basic_to_trim',
	'enforce_land_cap',
	'is_color_fixing_land',
	'weighted_sample_without_replacement',
	'count_existing_fetches',
	'select_top_land_candidates',
]


def compute_adjusted_target(category_label: str,
                            original_cfg: int,
                            existing: int,
                            output_func,
                            plural_word: str | None = None,
                            bonus_max_pct: float = 0.2,
                            rng=None) -> tuple[int, int]:
	"""Compute how many additional cards of a category to add applying a random bonus.

	Returns (to_add, bonus). to_add may be 0 if target already satisfied and bonus doesn't push above existing.

	Parameters
	----------
	category_label : str
		Human-readable label (e.g. 'Ramp', 'Removal').
	original_cfg : int
		Configured target count.
	existing : int
		How many already present.
	output_func : callable
		Function for emitting messages (e.g. print or logger).
	plural_word : str | None
		Phrase used in messages for plural additions. If None derives from label (lower + ' spells').
	bonus_max_pct : float
		Upper bound for random bonus percent (default 0.2 => up to +20%).
	rng : object | None
		Optional random-like object with uniform().
	"""
	if original_cfg <= 0:
		return 0, 0
	plural_word = plural_word or f"{category_label.lower()} spells"
	# Random bonus between 0 and bonus_max_pct inclusive
	roll = (rng.uniform(0.0, bonus_max_pct) if rng else _rand.uniform(0.0, bonus_max_pct))
	bonus = math.ceil(original_cfg * roll) if original_cfg > 0 else 0
	if existing >= original_cfg:
		to_add = original_cfg + bonus - existing
		if to_add <= 0:
			output_func(f"{category_label} target met ({existing}/{original_cfg}). Random bonus {bonus} -> no additional {plural_word} needed.")
			return 0, bonus
		output_func(f"{category_label} target met ({existing}/{original_cfg}). Adding random bonus {bonus}; scheduling {to_add} extra {plural_word}.")
		return to_add, bonus
	remaining_need = original_cfg - existing
	to_add = remaining_need + bonus
	output_func(f"Existing {category_label.lower()} {existing}/{original_cfg}. Remaining need {remaining_need}. Random bonus {bonus}. Adding {to_add} {plural_word}.")
	return to_add, bonus


def tapped_land_penalty(tline: str, text_field: str) -> tuple[int, int]:
	"""Classify a land for tapped optimization.

	Returns (tapped_flag, penalty). tapped_flag is 1 if the land counts toward
	the tapped threshold. Penalty is higher for worse (slower) lands. Non-tapped
	lands return (0, 0).
	"""
	tline_l = tline.lower()
	text_l = text_field.lower()
	if 'land' not in tline_l:
		return 0, 0
	always_tapped = 'enters the battlefield tapped' in text_l
	shock_like = 'you may pay 2 life' in text_l  # shocks can be untapped
	conditional = any(kw in text_l for kw in ['unless you control', 'if you control', 'as long as you control']) or shock_like
	tapped_flag = 0
	if always_tapped and not shock_like:
		tapped_flag = 1
	elif conditional:
		tapped_flag = 1
	if not tapped_flag:
		return 0, 0
	tri_types = sum(1 for b in bc.BASIC_LAND_TYPE_KEYWORDS if b in tline_l) >= 3
	any_color = any(p in text_l for p in bc.ANY_COLOR_MANA_PHRASES)
	cycling = 'cycling' in text_l
	life_gain = 'gain' in text_l and 'life' in text_l and 'you gain' in text_l
	produces_basic_colors = any(sym in text_l for sym in bc.COLORED_MANA_SYMBOLS)
	penalty = 8 if always_tapped and not conditional else 6
	if tri_types:
		penalty -= 3
	if any_color:
		penalty -= 3
	if cycling:
		penalty -= 2
	if conditional:
		penalty -= 2
	if not produces_basic_colors and not any_color:
		penalty += 1
	if life_gain:
		penalty += 1
	return tapped_flag, penalty


def replacement_land_score(name: str, tline: str, text_field: str) -> int:
	"""Heuristic scoring of candidate replacement lands (higher is better)."""
	tline_l = tline.lower()
	text_l = text_field.lower()
	score = 0
	lname = name.lower()
	# Prioritize shocks explicitly
	if any(kw in lname for kw in ['blood crypt', 'steam vents', 'watery grave', 'breeding pool', 'godless shrine', 'hallowed fountain', 'overgrown tomb', 'stomping ground', 'temple garden', 'sacred foundry']):
		score += 20
	if 'you may pay 2 life' in text_l:
		score += 15
	if any(p in text_l for p in bc.ANY_COLOR_MANA_PHRASES):
		score += 10
	types_present = [b for b in bc.BASIC_LAND_TYPE_KEYWORDS if b in tline_l]
	score += len(types_present) * 3
	if 'unless you control' in text_l:
		score += 2
	if 'cycling' in text_l:
		score += 1
	return score


def is_color_fixing_land(tline: str, text_lower: str) -> bool:
	"""Heuristic to detect if a land significantly fixes colors.

	Criteria:
	  - Two or more basic land types
	  - Produces any color (explicit text)
	  - Text shows two or more distinct colored mana symbols
	"""
	basic_count = sum(1 for bk in bc.BASIC_LAND_TYPE_KEYWORDS if bk in tline.lower())
	if basic_count >= 2:
		return True
	if any(p in text_lower for p in bc.ANY_COLOR_MANA_PHRASES):
		return True
	distinct = {cw for cw in bc.COLORED_MANA_SYMBOLS if cw in text_lower}
	return len(distinct) >= 2

# ---------------------------------------------------------------------------
# Weighted sampling & fetch helpers
# ---------------------------------------------------------------------------
def weighted_sample_without_replacement(pool: list[tuple[str, int | float]], k: int, rng=None) -> list[str]:
	"""Sample up to k unique names from (name, weight) pool without replacement.

	If total weight becomes 0, stops early. Stable for small pools used here.
	"""
	if k <= 0 or not pool:
		return []
	# _rand imported at module level
	local_rng = rng if rng is not None else _rand
	working = pool.copy()
	chosen: list[str] = []
	while working and len(chosen) < k:
		total_w = sum(max(0, float(w)) for _, w in working)
		if total_w <= 0:
			break
		r = local_rng.random() * total_w
		acc = 0.0
		pick_idx = 0
		for idx, (nm, w) in enumerate(working):
			acc += max(0, float(w))
			if r <= acc:
				pick_idx = idx
				break
		nm, _w = working.pop(pick_idx)
		chosen.append(nm)
	return chosen

# -----------------------------
# Land Debug Export Helper
# -----------------------------
def export_current_land_pool(builder, label: str) -> None:
	"""Write a CSV snapshot of current land candidates (full dataframe filtered to lands).

	Outputs to logs/debug/land_step_{label}_test.csv. Guarded so it only runs if the combined
	dataframe exists. Designed for diagnosing filtering shrinkage between land steps.
	"""
	try:  # pragma: no cover - diagnostics
		df = getattr(builder, '_combined_cards_df', None)
		if df is None or getattr(df, 'empty', True):
			return
		col = 'type' if 'type' in df.columns else ('type_line' if 'type_line' in df.columns else None)
		if not col:
			return
		land_df = df[df[col].fillna('').str.contains('Land', case=False, na=False)].copy()
		if land_df.empty:
			return
		import os
		os.makedirs(os.path.join('logs','debug'), exist_ok=True)
		export_cols = [c for c in ['name','type','type_line','manaValue','edhrecRank','colorIdentity','manaCost','themeTags','oracleText'] if c in land_df.columns]
		path = os.path.join('logs','debug', f'land_step_{label}_test.csv')
		try:
			if export_cols:
				land_df[export_cols].to_csv(path, index=False, encoding='utf-8')
			else:
				land_df.to_csv(path, index=False, encoding='utf-8')
		except Exception:
			land_df.to_csv(path, index=False)
		try:
			builder.output_func(f"[DEBUG] Wrote land_step_{label}_test.csv ({len(land_df)} rows)")
		except Exception:
			pass
	except Exception:
		pass


def count_existing_fetches(card_library: dict) -> int:
	bc = __import__('deck_builder.builder_constants', fromlist=['FETCH_LAND_MAX_CAP'])
	total = 0
	generic = getattr(bc, 'GENERIC_FETCH_LANDS', [])
	for n in generic:
		if n in card_library:
			total += card_library[n].get('Count', 1)
	for seq in getattr(bc, 'COLOR_TO_FETCH_LANDS', {}).values():
		for n in seq:
			if n in card_library:
				total += card_library[n].get('Count', 1)
	return total


def select_top_land_candidates(df, already: set[str], basics: set[str], top_n: int) -> list[tuple[int,str,str,str]]:
	"""Return list of (edh_rank, name, type_line, text_lower) for top_n remaining lands.

	Falls back to large rank number if edhrecRank missing/unparseable.
	"""
	out: list[tuple[int,str,str,str]] = []
	if df is None or getattr(df, 'empty', True):
		return out
	for _, row in df.iterrows():
		try:
			name = str(row.get('name',''))
			if not name or name in already or name in basics:
				continue
			tline = str(row.get('type', row.get('type_line','')))
			if 'land' not in tline.lower():
				continue
			edh = row.get('edhrecRank') if 'edhrecRank' in df.columns else None
			try:
				edh_val = int(edh) if edh not in (None,'','nan') else 999999
			except Exception:
				edh_val = 999999
			text_lower = str(row.get('text', row.get('oracleText',''))).lower()
			out.append((edh_val, name, tline, text_lower))
		except Exception:
			continue
	out.sort(key=lambda x: x[0])
	return out[:top_n]


# ---------------------------------------------------------------------------
# Misc land filtering helpers (mono-color exclusions & tribal weighting)
# ---------------------------------------------------------------------------
def is_mono_color(builder) -> bool:
	try:
		ci = getattr(builder, 'color_identity', []) or []
		return len([c for c in ci if c in ('W','U','B','R','G')]) == 1
	except Exception:
		return False


def has_kindred_theme(builder) -> bool:
	try:
		tags = [t.lower() for t in (getattr(builder, 'selected_tags', []) or [])]
		return any(('kindred' in t or 'tribal' in t) for t in tags)
	except Exception:
		return False


def is_kindred_land(name: str) -> bool:
	"""Return True if the land is considered kindred-oriented (unified constant)."""
	from . import builder_constants as bc  # local import to avoid cycles
	kindred = set(getattr(bc, 'KINDRED_LAND_NAMES', [])) or {d['name'] for d in getattr(bc, 'KINDRED_STAPLE_LANDS', [])}
	return name in kindred


def misc_land_excluded_in_mono(builder, name: str) -> bool:
	"""Return True if a land should be excluded in mono-color decks per constant list.

	Exclusion rules:
	  - Only applies if deck is mono-color.
	  - Never exclude items in MONO_COLOR_MISC_LAND_KEEP_ALWAYS.
	  - Never exclude tribal/kindred lands (they may be down-weighted separately if no theme).
	  - Always exclude The World Tree if not 5-color identity.
	"""
	from . import builder_constants as bc
	try:
		ci = getattr(builder, 'color_identity', []) or []
		# World Tree legality check (needs all five colors in identity)
		if name == 'The World Tree' and set(ci) != {'W','U','B','R','G'}:
			return True
		if not is_mono_color(builder):
			return False
		if name in getattr(bc, 'MONO_COLOR_MISC_LAND_KEEP_ALWAYS', []):
			return False
		if is_kindred_land(name):
			return False
		if name in getattr(bc, 'MONO_COLOR_MISC_LAND_EXCLUDE', []):
			return True
	except Exception:
		return False
	return False


def adjust_misc_land_weight(builder, name: str, base_weight: int | float) -> int | float:
	"""Adjust weight for tribal lands when no tribal theme present.

	If land is tribal and no kindred theme, weight is reduced (min 1) by factor.
	"""
	if is_kindred_land(name) and not has_kindred_theme(builder):
		try:
			# Ensure we don't drop below 1 (else risk exclusion by sampling step)
			return max(1, int(base_weight * 0.5))
		except Exception:
			return base_weight
	return base_weight


# ---------------------------------------------------------------------------
# Generic DataFrame helpers (tag normalization & sorting)
# ---------------------------------------------------------------------------
def normalize_tag_cell(cell):
	"""Normalize a themeTags-like cell into a lowercase list of tags.

	Accepts list, nested list, or string forms. Mirrors logic previously in multiple
	methods inside builder.py.
	"""
	if isinstance(cell, list):
		out: list[str] = []
		for v in cell:
			if isinstance(v, list):
				out.extend(str(x).strip().lower() for x in v if str(x).strip())
			else:
				vs = str(v).strip().lower()
				if vs:
					out.append(vs)
		return out
	if isinstance(cell, str):
		raw = cell.lower()
		for ch in '[]"':
			raw = raw.replace(ch, ' ')
		parts = [p.strip().strip("'\"") for p in raw.replace(';', ',').split(',') if p.strip()]
		return [p for p in parts if p]
	return []


def sort_by_priority(df, columns: list[str]):
	"""Sort DataFrame by listed columns ascending if present; ignores missing.

	Returns new DataFrame (does not mutate original)."""
	present = [c for c in columns if c in df.columns]
	if not present:
		return df
	return df.sort_values(by=present, ascending=[True]*len(present), na_position='last')


def _normalize_tags_list(tags: list[str]) -> list[str]:
	out: list[str] = []
	seen = set()
	for t in tags or []:
		tt = str(t).strip().lower()
		if tt and tt not in seen:
			out.append(tt)
			seen.add(tt)
	return out


def _color_subset_ok(required: list[str], commander_ci: list[str]) -> bool:
	if not required:
		return True
	ci = {c.upper() for c in commander_ci}
	need = {c.upper() for c in required}
	return need.issubset(ci)


def detect_viable_multi_copy_archetypes(builder) -> list[dict]:
	"""Return ranked viable multi-copy archetypes for the given builder.

	Output items: { id, name, printed_cap, type_hint, score, reasons }
	Never raises; returns [] on missing data.
	"""
	try:
		from . import builder_constants as bc
	except Exception:
		return []
	# Commander color identity and tags
	try:
		ci = list(getattr(builder, 'color_identity', []) or [])
	except Exception:
		ci = []
	# Gather tags from selected + commander summary
	tags: list[str] = []
	try:
		tags.extend([t for t in getattr(builder, 'selected_tags', []) or []])
	except Exception:
		pass
	try:
		cmd = getattr(builder, 'commander_dict', {}) or {}
		themes = cmd.get('Themes', [])
		if isinstance(themes, list):
			tags.extend(themes)
	except Exception:
		pass
	tags_norm = _normalize_tags_list(tags)
	out: list[dict] = []
	# Exclusivity prep: if multiple in same group qualify, we still compute score, suppression happens in consumer or by taking top one.
	for aid, meta in getattr(bc, 'MULTI_COPY_ARCHETYPES', {}).items():
		try:
			# Color gate
			if not _color_subset_ok(meta.get('color_identity', []), ci):
				continue
			# Tag triggers
			trig = meta.get('triggers', {}) or {}
			any_tags = _normalize_tags_list(trig.get('tags_any', []) or [])
			all_tags = _normalize_tags_list(trig.get('tags_all', []) or [])
			score = 0
			reasons: list[str] = []
			# +2 for color match baseline
			if meta.get('color_identity'):
				score += 2
				reasons.append('color identity fits')
			# +1 per matched any tag (cap small to avoid dwarfing)
			matches_any = [t for t in any_tags if t in tags_norm]
			if matches_any:
				bump = min(3, len(matches_any))
				score += bump
				reasons.append('tags: ' + ', '.join(matches_any[:3]))
			# +1 if all required tags matched
			if all_tags and all(t in tags_norm for t in all_tags):
				score += 1
				reasons.append('all required tags present')
			if score <= 0:
				continue
			out.append({
				'id': aid,
				'name': meta.get('name', aid),
				'printed_cap': meta.get('printed_cap'),
				'type_hint': meta.get('type_hint', 'noncreature'),
				'exclusive_group': meta.get('exclusive_group'),
				'default_count': meta.get('default_count', 25),
				'rec_window': meta.get('rec_window', (20,30)),
				'thrumming_stone_synergy': bool(meta.get('thrumming_stone_synergy', True)),
				'score': score,
				'reasons': reasons,
			})
		except Exception:
			continue
	# Suppress lower-scored siblings within the same exclusive group, keep the highest per group
	grouped: dict[str, list[dict]] = {}
	rest: list[dict] = []
	for item in out:
		grp = item.get('exclusive_group')
		if grp:
			grouped.setdefault(grp, []).append(item)
		else:
			rest.append(item)
	kept: list[dict] = rest[:]
	for grp, items in grouped.items():
		items.sort(key=lambda d: d.get('score', 0), reverse=True)
		kept.append(items[0])
	kept.sort(key=lambda d: d.get('score', 0), reverse=True)
	return kept


def prefer_owned_first(df, owned_names_lower: set[str], name_col: str = 'name'):
	"""Stable-reorder DataFrame to put owned names first while preserving prior sort.

	- Adds a temporary column to flag ownership, sorts by it desc with mergesort, then drops it.
	- If the name column is missing or owned_names_lower empty, returns df unchanged.
	"""
	try:
		if df is None or getattr(df, 'empty', True):
			return df
		if not owned_names_lower:
			return df
		if name_col not in df.columns:
			return df
		tmp_col = '_ownedPref'
		# Avoid clobbering if already present
		while tmp_col in df.columns:
			tmp_col = tmp_col + '_x'
		ser = df[name_col].astype(str).str.lower().isin(owned_names_lower).astype(int)
		df = df.assign(**{tmp_col: ser})
		df = df.sort_values(by=[tmp_col], ascending=[False], kind='mergesort')
		df = df.drop(columns=[tmp_col])
		return df
	except Exception:
		return df


# ---------------------------------------------------------------------------
# Tag-driven land suggestion helpers
# ---------------------------------------------------------------------------
def build_tag_driven_suggestions(builder) -> list[dict]:
	"""Return a list of suggestion dicts based on selected commander tags.

	Each dict fields:
	  name, reason, condition (callable taking builder), flex (bool), defer_if_full (bool)
	"""
	tags_lower = [t.lower() for t in getattr(builder, 'selected_tags', [])]
	existing = set(builder.card_library.keys())
	suggestions: list[dict] = []

	def cond_always(_):
		return True

	def cond_artifact_threshold(b):
		art_count = sum(1 for v in b.card_library.values() if 'artifact' in str(v.get('Card Type', '')).lower())
		return art_count >= 10

	mapping = [
		(['+1/+1 counters', 'counters matter'], 'Gavony Township', cond_always, '+1/+1 Counters support', True),
		(['token', 'tokens', 'wide'], 'Castle Ardenvale', cond_always, 'Token strategy support', True),
		(['graveyard', 'recursion', 'reanimator'], 'Boseiju, Who Endures', cond_always, 'Graveyard interaction / utility', False),
		(['graveyard', 'recursion', 'reanimator'], 'Takenuma, Abandoned Mire', cond_always, 'Recursion utility', True),
		(['artifact'], "Inventors' Fair", cond_artifact_threshold, 'Artifact payoff (conditional)', True),
	]
	for tag_keys, land_name, condition, reason, flex in mapping:
		if any(k in tl for k in tag_keys for tl in tags_lower):
			if land_name not in existing:
				suggestions.append({
					'name': land_name,
					'reason': reason,
					'condition': condition,
					'flex': flex,
					'defer_if_full': True
				})
	# Landfall fetch cap soft bump (side-effect set on builder)
	if any('landfall' in tl for tl in tags_lower) and not hasattr(builder, '_landfall_fetch_bump_applied'):
		setattr(builder, '_landfall_fetch_bump_applied', True)
		builder.dynamic_fetch_cap = getattr(__import__('deck_builder.builder_constants', fromlist=['FETCH_LAND_MAX_CAP']), 'FETCH_LAND_MAX_CAP', 7) + 1  # safe fallback
	return suggestions


# ---------------------------------------------------------------------------
# Color balance swap helpers
# ---------------------------------------------------------------------------
def select_color_balance_removal(builder, deficit_colors: set[str], overages: dict[str, float]) -> str | None:
	"""Select a land to remove when performing color balance swaps.

	Preference order:
	  1. Flex lands not producing any deficit colors
	  2. Basic land of the most overrepresented color
	  3. Mono-color non-flex land not producing deficit colors
	"""
	matrix_current = builder._compute_color_source_matrix()
	land_names = set(matrix_current.keys())  # ensure we only ever remove lands
	# Flex lands first
	for name, entry in builder.card_library.items():
		if name not in land_names:
			continue
		if entry.get('Role') == 'flex':
			colors = matrix_current.get(name, {})
			if not any(colors.get(c, 0) for c in deficit_colors):
				return name
	# Basic of most overrepresented color
	if overages:
		color_remove = max(overages.items(), key=lambda x: x[1])[0]
		basic_map = {'W': 'Plains', 'U': 'Island', 'B': 'Swamp', 'R': 'Mountain', 'G': 'Forest'}
		candidate = basic_map.get(color_remove)
		if candidate and candidate in builder.card_library and candidate in land_names:
			return candidate
	# Mono-color non-flex lands
	for name, entry in builder.card_library.items():
		if name not in land_names:
			continue
		if entry.get('Role') == 'flex':
			continue
		colors = matrix_current.get(name, {})
		color_count = sum(1 for v in colors.values() if v)
		if color_count <= 1 and not any(colors.get(c, 0) for c in deficit_colors):
			return name
	return None


def color_balance_addition_candidates(builder, target_color: str, combined_df) -> list[str]:
	"""Rank potential addition lands for a target color (best first)."""
	if combined_df is None or getattr(combined_df, 'empty', True):
		return []
	existing = set(builder.card_library.keys())
	out: list[tuple[str, int]] = []
	for _, row in combined_df.iterrows():
		name = str(row.get('name', ''))
		if not name or name in existing or any(name == o[0] for o in out):
			continue
		tline = str(row.get('type', row.get('type_line', ''))).lower()
		if 'land' not in tline:
			continue
		text_field = str(row.get('text', row.get('oracleText', ''))).lower()
		produces = False
		if target_color == 'W' and ('plains' in tline or '{w}' in text_field):
			produces = True
		if target_color == 'U' and ('island' in tline or '{u}' in text_field):
			produces = True
		if target_color == 'B' and ('swamp' in tline or '{b}' in text_field):
			produces = True
		if target_color == 'R' and ('mountain' in tline or '{r}' in text_field):
			produces = True
		if target_color == 'G' and ('forest' in tline or '{g}' in text_field):
			produces = True
		if not produces:
			continue
		any_color = 'add one mana of any color' in text_field
		basic_types = sum(1 for b in bc.BASIC_LAND_TYPE_KEYWORDS if b in tline)
		score = 0
		if any_color:
			score += 30
		score += basic_types * 10
		if 'enters the battlefield tapped' in text_field and 'you may pay 2 life' not in text_field:
			score -= 5
		out.append((name, score))
	out.sort(key=lambda x: x[1], reverse=True)
	return [n for n, _ in out]


# ---------------------------------------------------------------------------
# Basic land / land cap helpers
# ---------------------------------------------------------------------------
def basic_land_names() -> set[str]:
	names = set(getattr(__import__('deck_builder.builder_constants', fromlist=['BASIC_LANDS']), 'BASIC_LANDS', []))
	names.update(getattr(__import__('deck_builder.builder_constants', fromlist=['SNOW_BASIC_LAND_MAPPING']), 'SNOW_BASIC_LAND_MAPPING', {}).values())
	names.add('Wastes')
	return names


def count_basic_lands(card_library: dict) -> int:
	basics = basic_land_names()
	total = 0
	for name, entry in card_library.items():
		if name in basics:
			total += entry.get('Count', 1)
	return total


def choose_basic_to_trim(card_library: dict) -> str | None:
	basics = basic_land_names()
	candidates: list[tuple[int, str]] = []
	for name, entry in card_library.items():
		if name in basics:
			cnt = entry.get('Count', 1)
			if cnt > 0:
				candidates.append((cnt, name))
	if not candidates:
		return None
	candidates.sort(reverse=True)
	return candidates[0][1]


def enforce_land_cap(builder, step_label: str = ""):
	if not hasattr(builder, 'ideal_counts') or not getattr(builder, 'ideal_counts'):
		return
	bc = __import__('deck_builder.builder_constants', fromlist=['DEFAULT_LAND_COUNT'])
	land_target = builder.ideal_counts.get('lands', getattr(bc, 'DEFAULT_LAND_COUNT', 35))
	min_basic = builder.ideal_counts.get('basic_lands', getattr(bc, 'DEFAULT_BASIC_LAND_COUNT', 20))
	# math not needed; using ceil via BASIC_FLOOR_FACTOR logic only
	floor_basics = math.ceil(bc.BASIC_FLOOR_FACTOR * min_basic)
	current_land = builder._current_land_count()
	if current_land <= land_target:
		return
	builder.output_func(f"\nLand Cap Enforcement after {step_label}: Over target ({current_land}/{land_target}). Trimming basics...")
	removed = 0
	while current_land > land_target:
		basic_total = count_basic_lands(builder.card_library)
		if basic_total <= floor_basics:
			builder.output_func(f"Stopped trimming: basic lands at floor {basic_total} (floor {floor_basics}). Still {current_land}/{land_target}.")
			break
		target_basic = choose_basic_to_trim(builder.card_library)
		if not target_basic or not builder._decrement_card(target_basic):
			builder.output_func("No basic lands available to trim further.")
			break
		removed += 1
		current_land = builder._current_land_count()
	if removed:
		builder.output_func(f"Trimmed {removed} basic land(s). New land count: {current_land}/{land_target}. Basic total now {count_basic_lands(builder.card_library)} (floor {floor_basics}).")

