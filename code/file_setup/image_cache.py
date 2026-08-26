"""
Card image caching system.

Downloads and manages local cache of Magic: The Gathering card images
from Scryfall, with graceful fallback to API when images are missing.

Features:
- Optional caching (disabled by default for open source users)
- Uses Scryfall bulk data API (respects rate limits and guidelines)
- Downloads from Scryfall CDN (no rate limits on image files)
- Progress tracking for long downloads
- Resume capability if interrupted
- Graceful fallback to API if images missing

Environment Variables:
    CACHE_CARD_IMAGES: 1=enable caching, 0=disable (default: 0)
    IMAGE_CACHE_MODE: 'default'=cache only the best-scoring printing per card
        (legacy footprint, ~3.4 GB), 'full'=cache every paper printing of
        every card (~12-16 GB). Default: 'default'.

Image Sizes:
    - small: 160px width (for list views)
    - normal: 488px width (for prominent displays, hover previews)

Directory Structure (new, per-card/per-printing layout):
    card_files/images/{Card Name}/small/{scryfall_id}.jpg
    card_files/images/{Card Name}/normal/{scryfall_id}.jpg
    card_files/processed/card_printings.parquet   - printings metadata index

Legacy flat-file layout (still read as a fallback for cards not yet
migrated to the new layout):
    card_files/images/small/{Card Name}.jpg
    card_files/images/normal/{Card Name}.jpg

See: https://scryfall.com/docs/api
"""

import json
import logging
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Generator, Optional
from urllib.request import Request, urlopen

from code.file_setup.scryfall_bulk_data import ScryfallBulkDataClient
from code.file_setup.token_setup import _normalize_str, _token_text_fingerprint
from code.path_util import card_files_processed_dir

logger = logging.getLogger(__name__)

# Scryfall CDN (cards.scryfall.io) has no hard rate limits.
# We use a small delay to be a polite CDN citizen.
DOWNLOAD_DELAY = 0.025  # 25ms between image downloads (~40 req/sec)

# Image sizes to cache
IMAGE_SIZES = ["small", "normal"]

# Valid values for IMAGE_CACHE_MODE
VALID_CACHE_MODES = ("default", "full")

# Card name sanitization (filesystem-safe)
INVALID_CHARS = r'[<>:"/\\|?*]'

# Scryfall layouts that are token/emblem entries, not real cards (roadmap_39,
# Milestone 3). 'flip' is only a token when its type_line says so -- real flip
# cards never have "Token" in their type line.
_TOKEN_LAYOUTS = ("token", "double_faced_token", "emblem")


def _is_token_scryfall_entry(card: dict[str, Any]) -> bool:
    """True if a Scryfall bulk-data entry is a token/emblem, not a real card."""
    layout = card.get("layout")
    if layout in _TOKEN_LAYOUTS:
        return True
    return layout == "flip" and "Token" in (card.get("type_line") or "")


def _token_identity_key(
    name: Any, type_: Any, power: Any, toughness: Any, colors: Any = "", text: Any = "",
) -> tuple[str, str, str, str, str, str]:
    """Normalized (name, type, power, toughness, colors, text_hash) bridge key shared by the catalog and Scryfall sides."""
    def _pt(value: Any) -> str:
        if value is None or (isinstance(value, float) and value != value):  # NaN check without pandas
            return ""
        return str(value)

    def _colors(value: Any) -> str:
        if value is None:
            return ""
        try:
            items = [str(c).strip().upper() for c in list(value) if str(c or "").strip()]
        except TypeError:
            return str(value).strip().upper()
        return "".join(sorted(items))

    return (
        _normalize_str(name).lower(), _normalize_str(type_).lower(), _pt(power), _pt(toughness), _colors(colors),
        _token_text_fingerprint(text),
    )


def _build_token_identity_index(tokens_df) -> dict[tuple[str, str, str, str, str, str], tuple[str, str, str, str, str, str, str]]:
    """Map a normalized identity key to (catalog name, face name, type, power, toughness, colors, text).

    Both faces of a dual-faced token are indexed independently (each has its own
    Scryfall image), mirroring how real DFCs are already handled in
    `card_printings.parquet`. Many tokens share a display name but are
    genuinely different identities (e.g. "Elemental" has 9+ distinct
    power/toughness combos, several "Soldier" 1/1s with different types, a
    white 1/1 Soldier vs. a red/white 1/1 Soldier that share both type and
    stats, or a vanilla 1/1 Fish vs. one that "can't be blocked" sharing
    everything but ability text) -- type/power/toughness/colors/text are
    carried through so downstream code can tell them apart instead of
    collapsing by name alone.
    """
    import pandas as pd

    index: dict[tuple[str, str, str, str, str, str], tuple[str, str, str, str, str, str, str]] = {}
    for row in tokens_df.itertuples(index=False):
        # NaN check, not truthiness: missing faceName_a can read back as
        # `float("nan")` instead of `None` depending on the pandas/pyarrow
        # version's string-dtype null handling, and `bool(float("nan"))` is
        # True, which would misroute every single-faced row into the
        # dual-faced branch below.
        face_a = getattr(row, "faceName_a", None)
        colors = getattr(row, "colors", None)
        if pd.notna(face_a) and face_a:
            face_a_text = getattr(row, "face_a_text", "") or ""
            face_b_text = getattr(row, "face_b_text", "") or ""
            index[_token_identity_key(row.faceName_a, row.face_a_type, row.face_a_power, row.face_a_toughness, colors, face_a_text)] = (
                row.name, row.faceName_a, row.face_a_type, row.face_a_power, row.face_a_toughness, colors, face_a_text,
            )
            index[_token_identity_key(row.faceName_b, row.face_b_type, row.face_b_power, row.face_b_toughness, colors, face_b_text)] = (
                row.name, row.faceName_b, row.face_b_type, row.face_b_power, row.face_b_toughness, colors, face_b_text,
            )
        else:
            text = getattr(row, "text", "") or ""
            index[_token_identity_key(row.name, row.type, row.power, row.toughness, colors, text)] = (
                row.name, row.name, row.type, row.power, row.toughness, colors, text,
            )
    return index


def get_cache_mode() -> str:
    """
    Return the configured image cache mode.

    'default': only the single highest-scoring printing per card is cached
        (matches today's footprint, ~3.4 GB), just stored in the new
        per-card/per-printing folder layout instead of a flat filename.
    'full': every paper printing of every card is cached (~12-16 GB).

    Returns:
        'default' or 'full'

    Raises:
        ValueError: If IMAGE_CACHE_MODE is set to an unrecognized value.
    """
    mode = os.getenv("IMAGE_CACHE_MODE", "default").strip().lower()
    if mode not in VALID_CACHE_MODES:
        raise ValueError(
            f"Invalid IMAGE_CACHE_MODE '{mode}'; expected one of {VALID_CACHE_MODES}"
        )
    return mode


def sanitize_filename(card_name: str) -> str:
    """
    Sanitize card name for use as filename.

    Args:
        card_name: Original card name

    Returns:
        Filesystem-safe filename
    """
    # Replace invalid characters with underscore
    safe_name = re.sub(INVALID_CHARS, "_", card_name)
    # Remove multiple consecutive underscores
    safe_name = re.sub(r"_+", "_", safe_name)
    # Trim leading/trailing underscores
    safe_name = safe_name.strip("_")
    return safe_name


class ImageCache:
    """Manages local card image cache."""

    def __init__(
        self,
        base_dir: str = "card_files/images",
        bulk_data_path: str = "card_files/raw/scryfall_bulk_data.json",
    ):
        """
        Initialize image cache.

        Args:
            base_dir: Base directory for cached images
            bulk_data_path: Path to Scryfall bulk data JSON
        """
        self.base_dir = Path(base_dir)
        self.bulk_data_path = Path(bulk_data_path)
        self.client = ScryfallBulkDataClient()
        self._last_download_time: float = 0.0

        # Printings metadata index (new per-card/per-printing layout).
        self.printings_index_path = Path(card_files_processed_dir()) / "card_printings.parquet"
        self._printings_df = None  # lazily loaded pandas DataFrame

        # Token/emblem printings index + image tree -- kept fully separate from
        # the real-card cache above (roadmap_39, Milestone 3).
        self.token_base_dir = self.base_dir / "tokens"
        self.token_printings_index_path = Path(card_files_processed_dir()) / "token_printings.parquet"
        self._token_printings_df = None  # lazily loaded pandas DataFrame

        # In-memory index of available images (avoids repeated filesystem checks)
        # Key: (size, sanitized_filename), Value: True if exists
        self._image_index: dict[tuple[str, str], bool] = {}
        self._index_built = False

    def is_enabled(self) -> bool:
        """Check if image caching is enabled via environment variable."""
        return os.getenv("CACHE_CARD_IMAGES", "0") == "1"
    
    def _build_image_index(self) -> None:
        """
        Build in-memory index of cached images to avoid repeated filesystem checks.
        This dramatically improves performance by eliminating stat() calls for every image.
        """
        if self._index_built or not self.is_enabled():
            return
        
        logger.info("Building image cache index...")
        start_time = time.time()
        
        for size in IMAGE_SIZES:
            size_dir = self.base_dir / size
            if not size_dir.exists():
                continue
            
            # Scan directory for .jpg files
            for image_file in size_dir.glob("*.jpg"):
                # Store just the filename without extension
                filename = image_file.stem
                self._image_index[(size, filename)] = True
        
        elapsed = time.time() - start_time
        total_images = len(self._image_index)
        logger.info(f"Image index built: {total_images} images indexed in {elapsed:.3f}s")
        self._index_built = True

    def get_image_path(self, card_name: str, size: str = "normal") -> Optional[Path]:
        """
        Get local path to cached image if it exists.

        Args:
            card_name: Card name
            size: Image size ('small' or 'normal')

        Returns:
            Path to cached image, or None if not cached
        """
        if not self.is_enabled():
            return None
        
        # Build index on first access (lazy initialization)
        if not self._index_built:
            self._build_image_index()

        safe_name = sanitize_filename(card_name)
        
        # Check in-memory index first (fast) -- legacy flat-file layout.
        if (size, safe_name) in self._image_index:
            return self.base_dir / size / f"{safe_name}.jpg"

        # New per-card/per-printing layout: fall back to the default
        # (highest-scoring) printing on disk, if the printings index has
        # been built and that image has already been downloaded. This is
        # a pure existence check (no on-demand download) -- callers that
        # want download-on-miss should use get_printing_image_path()
        # directly (see the /api/images route).
        default_id = self.get_default_printing_id(card_name)
        if default_id:
            candidate = self.get_printing_image_path(card_name, default_id, size)
            if candidate.exists():
                return candidate

        return None

    def get_image_url(self, card_name: str, size: str = "normal") -> str:
        """
        Get image URL (local path if cached, Scryfall API otherwise).

        Args:
            card_name: Card name
            size: Image size ('small' or 'normal')

        Returns:
            URL or local path to image
        """
        # Check local cache first
        local_path = self.get_image_path(card_name, size)
        if local_path:
            # Return as static file path for web serving
            return f"/static/card_images/{size}/{sanitize_filename(card_name)}.jpg"

        # Fallback to Scryfall API
        from urllib.parse import quote
        card_query = quote(card_name)
        return f"https://api.scryfall.com/cards/named?fuzzy={card_query}&format=image&version={size}"

    def _rate_limit_wait(self) -> None:
        """Wait to respect rate limits between downloads."""
        elapsed = time.time() - self._last_download_time
        if elapsed < DOWNLOAD_DELAY:
            time.sleep(DOWNLOAD_DELAY - elapsed)
        self._last_download_time = time.time()

    def _download_image(self, image_url: str, output_path: Path) -> bool:
        """
        Download single image from Scryfall CDN.

        Args:
            image_url: Image URL from bulk data
            output_path: Local path to save image

        Returns:
            True if successful, False otherwise
        """
        self._rate_limit_wait()

        try:
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            req = Request(image_url)
            req.add_header("User-Agent", "MTG-Deckbuilder/3.0 (Image Cache)")

            with urlopen(req, timeout=30) as response:
                with open(output_path, "wb") as f:
                    shutil.copyfileobj(response, f, length=65536)

            return True

        except Exception as e:
            logger.debug(f"Failed to download {image_url}: {e}")
            # Clean up partial download
            if output_path.exists():
                output_path.unlink()
            return False

    # Frame effects that mark a non-standard treatment (showcase, extended-art, etc.).
    _SPECIAL_FRAME_EFFECTS: frozenset[str] = frozenset(
        {"showcase", "extendedart", "inverted", "step_and_compleat_foil",
         "etched", "sunmoondfc", "compasslandmark", "mooneldraziclock"}
    )

    # Scryfall set_types whose cards are stylized/reskinned products (Secret
    # Lair drops, masterpiece series, etc.) even when other fields (border,
    # full_art) look "standard". These should never win over a genuine
    # normal-set printing.
    _NON_STANDARD_SET_TYPES: frozenset[str] = frozenset(
        {"box", "masterpiece", "memorabilia", "spellbook",
         "from_the_vault", "premium_deck", "duel_deck", "arsenal"}
    )

    def _score_printing(self, card: dict[str, Any]) -> int:
        """
        Score a printing by how "standard" it looks.

        Higher = more standard frame, preferred for image caching.
        Fields used: full_art, textless, promo, border_color, booster,
        variation, frame_effects, set_type.
        """
        score = 0
        if not card.get("full_art", False):
            score += 6
        if not card.get("textless", False):
            score += 2
        if not card.get("promo", False):
            score += 2
        if card.get("border_color") == "black":
            score += 3
        if card.get("booster", False):
            score += 1
        if not card.get("variation", False):
            score += 1
        if card.get("set_type") not in self._NON_STANDARD_SET_TYPES:
            score += 3
        frame_effects = card.get("frame_effects") or []
        if not any(e in self._SPECIAL_FRAME_EFFECTS for e in frame_effects):
            score += 2
        return score

    def _stream_card_image_data(
        self,
    ) -> Generator[tuple[str, dict[str, str]], None, None]:
        """
        Stream image URI data for our cards from bulk JSON, yielding the most
        standard-looking printing per card name.

        Does a single pass through the bulk JSON, scoring each printing with
        `_score_printing` and keeping only the best-scoring one per card name.
        Only minimal data (image URIs + card name) is retained, so peak RAM
        stays in the tens-of-MB range. Yields (face_name, image_uris) tuples
        for the chosen printing of every card in our dataset.

        Raises:
            FileNotFoundError: If bulk data file doesn't exist.
        """
        if not self.bulk_data_path.exists():
            raise FileNotFoundError(
                f"Bulk data file not found: {self.bulk_data_path}. "
                "Run download_bulk_data() first."
            )

        # Load only card names from parquet — a small set of strings.
        our_card_names: set[str] | None = None
        try:
            import pandas as pd
            from code.path_util import get_processed_cards_path

            parquet_path = get_processed_cards_path()
            df = pd.read_parquet(parquet_path, columns=["name"])
            our_card_names = set(df["name"].str.lower())
            logger.info(
                f"Streaming bulk data for {len(our_card_names)} cards in our dataset"
            )
        except Exception as e:
            logger.warning(f"Could not load card names from parquet: {e}. Streaming all cards.")

        # best: name_lower -> (score, [(face_name, image_uris)])
        # Stores only the minimal image URI data needed — not full card objects.
        best: dict[str, tuple[int, list[tuple[str, dict[str, str]]]]] = {}

        with open(self.bulk_data_path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip().rstrip(",")
                if not line or line in ("[", "]"):
                    continue
                try:
                    card = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Token-copy entries (Offspring/Embalm/Eternalize, etc.) can
                # share a real card's name (roadmap_39, Milestone 4) -- exclude
                # before the name-membership check so they never win the
                # best-printing slot for that real card.
                if _is_token_scryfall_entry(card):
                    continue

                card_name: str = card.get("name", "")
                if not card_name:
                    continue

                name_lower = card_name.lower()
                if our_card_names is not None and name_lower not in our_card_names:
                    continue

                # Collect image-URI faces for this printing.
                faces: list[tuple[str, dict[str, str]]] = []
                if card.get("image_uris"):
                    faces.append((card_name, card["image_uris"]))
                elif card.get("card_faces"):
                    for face in card["card_faces"]:
                        if face.get("image_uris"):
                            face_name: str = face.get("name", card_name)
                            faces.append((face_name, face["image_uris"]))

                if not faces:
                    continue

                score = self._score_printing(card)
                existing = best.get(name_lower)
                if existing is None or score > existing[0]:
                    best[name_lower] = (score, faces)

        # Yield the best printing for each card.
        for _score, faces in best.values():
            for face_name, image_uris in faces:
                yield face_name, image_uris

    def _stream_all_printings(self) -> Generator[dict[str, Any], None, None]:
        """
        Stream metadata for *every* paper (non-digital) printing of every
        card in our dataset -- unlike `_stream_card_image_data()`, this does
        not collapse multiple printings of the same card down to one.

        Only lightweight metadata is yielded (no image bytes), for building
        the `card_printings.parquet` index.

        Raises:
            FileNotFoundError: If bulk data file doesn't exist.
        """
        if not self.bulk_data_path.exists():
            raise FileNotFoundError(
                f"Bulk data file not found: {self.bulk_data_path}. "
                "Run download_bulk_data() first."
            )

        our_card_names: set[str] | None = None
        try:
            import pandas as pd
            from code.path_util import get_processed_cards_path

            parquet_path = get_processed_cards_path()
            df = pd.read_parquet(parquet_path, columns=["name"])
            our_card_names = set(df["name"].str.lower())
            logger.info(
                f"Streaming all printings for {len(our_card_names)} cards in our dataset"
            )
        except Exception as e:
            logger.warning(f"Could not load card names from parquet: {e}. Streaming all cards.")

        with open(self.bulk_data_path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip().rstrip(",")
                if not line or line in ("[", "]"):
                    continue
                try:
                    card = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if card.get("digital"):
                    continue  # paper printings only

                # Token-copy entries (Offspring/Embalm/Eternalize, etc.) can
                # share a real card's name (roadmap_39, Milestone 4) -- exclude
                # before the name-membership check so they never leak into
                # card_printings.parquet as a fake printing of the real card.
                if _is_token_scryfall_entry(card):
                    continue

                card_name: str = card.get("name", "")
                if not card_name:
                    continue

                name_lower = card_name.lower()
                if our_card_names is not None and name_lower not in our_card_names:
                    continue

                faces: list[tuple[str, dict[str, str]]] = []
                if card.get("image_uris"):
                    faces.append((card_name, card["image_uris"]))
                elif card.get("card_faces"):
                    for face in card["card_faces"]:
                        if face.get("image_uris"):
                            face_name: str = face.get("name", card_name)
                            faces.append((face_name, face["image_uris"]))

                if not faces:
                    continue

                score = self._score_printing(card)
                scryfall_id = card.get("id", "")
                for face_name, image_uris in faces:
                    yield {
                        "name": card_name,
                        "face_name": face_name,
                        "scryfall_id": scryfall_id,
                        "set": card.get("set", ""),
                        "set_name": card.get("set_name", ""),
                        "collector_number": card.get("collector_number", ""),
                        "released_at": card.get("released_at", ""),
                        "finishes": list(card.get("finishes") or []),
                        "score": score,
                        "image_url_small": image_uris.get("small", ""),
                        "image_url_normal": image_uris.get("normal", ""),
                    }

    def build_printings_index(self, output_path: Optional[str] = None) -> int:
        """
        Build the printings metadata index (`card_printings.parquet`),
        covering every paper printing of every card in our dataset.

        Always builds the *full* index regardless of `IMAGE_CACHE_MODE` --
        the index is metadata-only (no image bytes) and is needed by the
        printing picker even when only the default printing's image has
        been downloaded. Only `download_all_printings()` respects the mode.

        Args:
            output_path: Where to write the parquet file. Defaults to
                `self.printings_index_path`.

        Returns:
            Number of printing rows written.

        Raises:
            FileNotFoundError: If bulk data file doesn't exist.
        """
        import pandas as pd

        dest = Path(output_path) if output_path else self.printings_index_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        columns = [
            "name", "face_name", "scryfall_id", "set", "set_name",
            "collector_number", "released_at", "finishes", "score",
            "image_url_small", "image_url_normal", "is_default",
        ]

        rows = list(self._stream_all_printings())
        if not rows:
            logger.warning("No printings found while building printings index")
            pd.DataFrame(columns=columns).to_parquet(dest, index=False)
            return 0

        df = pd.DataFrame(rows)
        # Mark every row sharing the max score for its card name as the default
        # printing (may be more than one row on a tie -- same limitation as
        # today's flat-file cache's first-seen-wins tie-break).
        df["is_default"] = df.groupby("name")["score"].transform(lambda s: s == s.max())

        df.to_parquet(dest, index=False)
        self._printings_df = None  # invalidate in-memory cache
        logger.info(f"Wrote {len(df)} printing rows to {dest}")
        return len(df)

    def _load_printings_df(self):
        """Lazily load and cache the printings index DataFrame, or None if absent."""
        if self._printings_df is not None:
            return self._printings_df
        if not self.printings_index_path.exists():
            return None
        import pandas as pd

        self._printings_df = pd.read_parquet(self.printings_index_path)
        return self._printings_df

    def get_printings(self, card_name: str) -> list[dict[str, Any]]:
        """
        Return metadata for every known paper printing of a card (from the
        printings index), or an empty list if the index hasn't been built
        or the card has no rows.

        Values are plain JSON-serializable Python types (not numpy scalars),
        since this is consumed directly by JSON API responses.
        """
        df = self._load_printings_df()
        if df is None:
            return []
        matches = df[df["face_name"].str.lower() == card_name.lower()]
        if matches.empty:
            return []
        return json.loads(matches.to_json(orient="records"))

    def get_default_printing_id(self, card_name: str) -> Optional[str]:
        """Return the Scryfall ID of the default printing for a card.

        The default is the highest-scoring (most "standard-looking", see
        `_score_printing`) printing. Multiple printings can tie for the top
        score (e.g. several plain non-promo reprints across sets), so ties
        are broken by most recent `released_at` -- a current, in-print
        reprint's art is what most players expect as the default, rather
        than a decades-old original printing.
        """
        df = self._load_printings_df()
        if df is None:
            return None
        matches = df[(df["face_name"].str.lower() == card_name.lower()) & (df["is_default"])]
        if matches.empty:
            return None
        matches = matches.sort_values("released_at", ascending=False, na_position="last")
        return str(matches.iloc[0]["scryfall_id"])

    def get_printing_id_for_set(self, card_name: str, set_code: str) -> Optional[str]:
        """Return the Scryfall ID of the card's printing within `set_code`.

        Mirrors `get_default_printing_id()`'s tie-break (highest `score`,
        then most recent `released_at`) but scoped to a single set, so a
        `set:` search can show that set's own art instead of the card's
        globally-best printing. Returns `None` if the card has no printing
        in that set (or the printings index hasn't been built).
        """
        df = self._load_printings_df()
        if df is None:
            return None
        matches = df[
            (df["face_name"].str.lower() == card_name.lower())
            & (df["set"].str.upper() == set_code.upper())
        ]
        if matches.empty:
            return None
        matches = matches.sort_values(["score", "released_at"], ascending=[False, False], na_position="last")
        return str(matches.iloc[0]["scryfall_id"])

    def get_printing_meta(
        self, card_name: str, *, scryfall_id: Optional[str] = None, set_code: Optional[str] = None
    ) -> Optional[dict[str, str]]:
        """Return `{"set", "set_name", "collector_number"}` for one printing.

        Used by the set+collector-number tile/detail badge: looks up the
        exact printing by `scryfall_id` if given (so the badge matches
        whatever art is actually displayed); otherwise falls back to the
        same best-in-set match `get_printing_id_for_set()` uses (highest
        `score`, then most recent `released_at`). Returns `None` if nothing
        matches (or the printings index hasn't been built).
        """
        df = self._load_printings_df()
        if df is None:
            return None
        matches = df[df["face_name"].str.lower() == card_name.lower()]
        if scryfall_id:
            matches = matches[matches["scryfall_id"] == scryfall_id]
        elif set_code:
            matches = matches[matches["set"].str.upper() == set_code.upper()]
            matches = matches.sort_values(["score", "released_at"], ascending=[False, False], na_position="last")
        if matches.empty:
            return None
        row = matches.iloc[0]
        return {
            "set": str(row["set"]).upper(),
            "set_name": str(row["set_name"]),
            "collector_number": str(row["collector_number"]),
        }

    def get_printing_image_path(
        self, card_name: str, scryfall_id: str, size: str = "normal"
    ) -> Path:
        """Build the on-disk path for a specific printing's cached image (new layout)."""
        return self.base_dir / sanitize_filename(card_name) / size / f"{scryfall_id}.jpg"

    def backup_existing_cache(self, dest: Optional[Path] = None) -> Optional[Path]:
        """
        Move the current image cache directory aside before a fresh
        redownload into the new per-card/per-printing layout.

        Uses a rename (not copy) so it's near-instant and doesn't itself
        consume extra disk space -- only the subsequent redownload does.

        Args:
            dest: Backup destination. Defaults to
                `{base_dir.parent}/images_backup_{timestamp}`.

        Returns:
            The backup path, or None if there was nothing to back up.

        Raises:
            FileExistsError: If the backup destination already exists.
        """
        if not self.base_dir.exists():
            return None

        if dest is None:
            timestamp = time.strftime("%Y%m%dT%H%M%S")
            dest = self.base_dir.parent / f"images_backup_{timestamp}"
        dest = Path(dest)

        if dest.exists():
            raise FileExistsError(f"Backup destination already exists: {dest}")

        self.base_dir.rename(dest)
        self.invalidate_index()
        self.invalidate_summary_cache()
        logger.info(f"Backed up existing image cache to {dest}")
        return dest

    def download_all_printings(
        self,
        mode: Optional[str] = None,
        sizes: Optional[list[str]] = None,
        progress_callback=None,
        max_rows: Optional[int] = None,
    ) -> dict[str, int]:
        """
        Download images into the new per-card/per-printing folder layout
        (`card_files/images/{Card Name}/{size}/{scryfall_id}.jpg`), using
        the printings index built by `build_printings_index()`.

        Args:
            mode: 'default' (only the highest-scoring printing per card) or
                'full' (every paper printing). Defaults to IMAGE_CACHE_MODE
                env var (see `get_cache_mode()`).
            sizes: Image sizes to download (default: ['small', 'normal']).
            progress_callback: Optional callback(current, total, card_name).
            max_rows: Maximum printing rows to download (for testing).

        Returns:
            Dictionary with download statistics.

        Raises:
            FileNotFoundError: If the printings index hasn't been built yet.
            ValueError: If `mode` is not a recognized value.
        """
        if not self.is_enabled():
            logger.info("Image caching disabled (CACHE_CARD_IMAGES=0)")
            return {"skipped": 0}

        if not self.printings_index_path.exists():
            raise FileNotFoundError(
                f"Printings index not found: {self.printings_index_path}. "
                "Run build_printings_index() first."
            )

        resolved_mode = (mode or get_cache_mode()).strip().lower()
        if resolved_mode not in VALID_CACHE_MODES:
            raise ValueError(f"Invalid mode '{resolved_mode}'; expected one of {VALID_CACHE_MODES}")

        if sizes is None:
            sizes = IMAGE_SIZES

        import pandas as pd

        df = pd.read_parquet(self.printings_index_path)
        if resolved_mode == "default":
            df = df[df["is_default"]]
            # is_default can have multiple tied rows per card (same score);
            # keep exactly one per face_name, breaking ties by most recent
            # released_at -- matches get_default_printing_id()'s tie-break.
            df = df.sort_values("released_at", ascending=False, na_position="last")
            df = df.drop_duplicates(subset="face_name", keep="first")

        if max_rows is not None:
            df = df.head(max_rows)

        stats = {"total": len(df), "downloaded": 0, "skipped": 0, "failed": 0}

        for i, row in enumerate(df.itertuples(index=False)):
            card_folder = self.base_dir / sanitize_filename(row.face_name)
            for size in sizes:
                image_url = row.image_url_small if size == "small" else row.image_url_normal
                if not image_url:
                    continue

                output_path = card_folder / size / f"{row.scryfall_id}.jpg"
                if output_path.exists():
                    stats["skipped"] += 1
                    continue

                if self._download_image(image_url, output_path):
                    stats["downloaded"] += 1
                else:
                    stats["failed"] += 1

            if progress_callback:
                progress_callback(i + 1, len(df), row.face_name)

        # Regenerate the summary now (in this same background download thread)
        # rather than merely invalidating it -- otherwise the next /api/images/status
        # poll pays the full ~30s directory-scan cost itself.
        self.invalidate_summary_cache()
        self.invalidate_index()
        self.cache_statistics()

        logger.info(f"Printing-aware image download complete: {stats}")
        return stats

    def _stream_token_printings(self, tokens_df) -> Generator[dict[str, Any], None, None]:
        """
        Stream metadata for every paper printing of every token/emblem identity
        in `tokens_df`, bridging Scryfall bulk-data entries to Milestone-1 token
        identities by normalized (name, type, power, toughness) -- MTGJSON's
        token catalog has no Scryfall ID column to join on directly (see
        roadmap_39, Milestone 3).

        Raises:
            FileNotFoundError: If bulk data file doesn't exist.
        """
        if not self.bulk_data_path.exists():
            raise FileNotFoundError(
                f"Bulk data file not found: {self.bulk_data_path}. "
                "Run download_bulk_data() first."
            )

        identity_index = _build_token_identity_index(tokens_df)
        if not identity_index:
            return

        with open(self.bulk_data_path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip().rstrip(",")
                if not line or line in ("[", "]"):
                    continue
                try:
                    card = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if card.get("digital"):
                    continue  # paper printings only
                if not _is_token_scryfall_entry(card):
                    continue

                faces: list[dict[str, Any]] = []
                if card.get("card_faces"):
                    for face in card["card_faces"]:
                        # Some flip-role tokens (e.g. "Monster // Virtuous") only
                        # carry a single shared image at the top level, not per
                        # face -- fall back to it so both faces still bridge.
                        image_uris = face.get("image_uris") or card.get("image_uris")
                        if not image_uris:
                            continue
                        faces.append({
                            "face_name": face.get("name", ""),
                            "type_line": face.get("type_line", ""),
                            "power": face.get("power"),
                            "toughness": face.get("toughness"),
                            "colors": face.get("colors") if face.get("colors") is not None else card.get("colors"),
                            "text": face.get("oracle_text", ""),
                            "image_uris": image_uris,
                        })
                elif card.get("image_uris"):
                    faces.append({
                        "face_name": card.get("name", ""),
                        "type_line": card.get("type_line", ""),
                        "power": card.get("power"),
                        "toughness": card.get("toughness"),
                        "colors": card.get("colors"),
                        "text": card.get("oracle_text", ""),
                        "image_uris": card["image_uris"],
                    })
                if not faces:
                    continue

                score = self._score_printing(card)
                scryfall_id = card.get("id", "")
                for face in faces:
                    key = _token_identity_key(
                        face["face_name"], face["type_line"], face["power"], face["toughness"], face["colors"], face["text"],
                    )
                    match = identity_index.get(key)
                    if match is None:
                        continue
                    catalog_name, face_name, type_line, power, toughness, colors, text = match
                    image_uris = face["image_uris"]
                    yield {
                        "name": catalog_name,
                        "face_name": face_name,
                        # Catalog's own type/power/toughness/colors, not Scryfall's
                        # -- this is the disambiguator between same-named token
                        # variants (e.g. "Elemental" 1/1 vs 2/2, several "Soldier"
                        # 1/1s with different types, or a white vs. red/white
                        # 1/1 Soldier), so it must be stable across every
                        # printing of the same identity.
                        "type": type_line,
                        "power": power,
                        "toughness": toughness,
                        "colors": "".join(sorted(str(c).strip().upper() for c in list(colors) if str(c or "").strip())) if colors is not None else "",
                        "text_hash": _token_text_fingerprint(text),
                        "scryfall_id": scryfall_id,
                        "set": card.get("set", ""),
                        "set_name": card.get("set_name", ""),
                        "collector_number": card.get("collector_number", ""),
                        "released_at": card.get("released_at", ""),
                        "finishes": list(card.get("finishes") or []),
                        "score": score,
                        "image_url_small": image_uris.get("small", ""),
                        "image_url_normal": image_uris.get("normal", ""),
                    }

    def build_token_printings_index(self, tokens_df, output_path: Optional[str] = None) -> int:
        """
        Build the token/emblem printings metadata index (`token_printings.parquet`),
        bridging Milestone-1 catalog identities to Scryfall printings by name/type/
        power/toughness. Written to a separate parquet file, never merged into
        `card_printings.parquet` (see roadmap_39, Milestone 3).

        Args:
            tokens_df: The Milestone-1 token/emblem catalog DataFrame.
            output_path: Where to write the parquet file. Defaults to
                `self.token_printings_index_path`.

        Returns:
            Number of printing rows written.

        Raises:
            FileNotFoundError: If bulk data file doesn't exist.
        """
        import pandas as pd

        dest = Path(output_path) if output_path else self.token_printings_index_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        columns = [
            "name", "face_name", "type", "power", "toughness", "colors", "text_hash", "scryfall_id", "set", "set_name",
            "collector_number", "released_at", "finishes", "score",
            "image_url_small", "image_url_normal", "is_default",
        ]

        rows = list(self._stream_token_printings(tokens_df))
        if not rows:
            logger.warning("No token/emblem printings matched while building token printings index")
            pd.DataFrame(columns=columns).to_parquet(dest, index=False)
            return 0

        df = pd.DataFrame(rows)
        # Default printing is scoped per (face_name, type, power, toughness,
        # colors, text_hash), not face_name alone -- same-named tokens with
        # different stats (e.g. "Elemental" 1/1 vs 2/2), different types
        # (e.g. several "Soldier" 1/1s), different colors (e.g. white vs.
        # red/white 1/1 Soldier), or different ability text (e.g. a vanilla
        # 1/1 Fish vs. one that "can't be blocked") are different identities
        # and must each get their own default printing, not compete against
        # each other.
        # dropna=False: non-creature tokens/emblems have no power/toughness
        # (NaN), and groupby drops NaN-keyed groups by default, which would
        # otherwise leave `is_default` unset (None) for all of them.
        df["is_default"] = df.groupby(["face_name", "type", "power", "toughness", "colors", "text_hash"], dropna=False)["score"].transform(lambda s: s == s.max())

        df.to_parquet(dest, index=False)
        self._token_printings_df = None  # invalidate in-memory cache
        logger.info(f"Wrote {len(df)} token/emblem printing rows to {dest}")
        return len(df)

    def _load_token_printings_df(self):
        """Lazily load and cache the token printings index DataFrame, or None if absent."""
        if self._token_printings_df is not None:
            return self._token_printings_df
        if not self.token_printings_index_path.exists():
            return None
        import pandas as pd

        self._token_printings_df = pd.read_parquet(self.token_printings_index_path)
        return self._token_printings_df

    @staticmethod
    def _filter_token_stats(
        matches, power: Optional[str], toughness: Optional[str], type_line: Optional[str] = None,
        colors: Optional[str] = None, text_hash: Optional[str] = None,
    ):
        """Narrow a token-printings frame to a specific type/power/toughness/colors/text variant.

        Same-named tokens with different stats (e.g. "Elemental" 1/1 vs 2/2),
        different types (e.g. several "Soldier" 1/1s), different colors
        (e.g. white vs. red/white 1/1 Soldier), or different ability text
        (e.g. a vanilla 1/1 Fish vs. one that "can't be blocked") are
        different identities; omitting these matches every variant sharing
        the name instead of a single identity.
        """
        if power is not None:
            matches = matches[matches["power"].astype(str) == str(power)]
        if toughness is not None:
            matches = matches[matches["toughness"].astype(str) == str(toughness)]
        if type_line is not None and "type" in matches.columns:
            matches = matches[matches["type"].astype(str).str.lower() == str(type_line).lower()]
        if colors is not None and "colors" in matches.columns:
            normalized = "".join(sorted(colors.strip().upper()))
            matches = matches[matches["colors"].astype(str).apply(lambda v: "".join(sorted(v.strip().upper()))) == normalized]
        if text_hash is not None and "text_hash" in matches.columns:
            matches = matches[matches["text_hash"].astype(str) == str(text_hash)]
        return matches

    def get_token_printings(
        self, token_face_name: str, power: Optional[str] = None, toughness: Optional[str] = None,
        type_line: Optional[str] = None, colors: Optional[str] = None, text_hash: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return metadata for every known paper printing of a token/emblem identity."""
        df = self._load_token_printings_df()
        if df is None:
            return []
        matches = df[df["face_name"].str.lower() == token_face_name.lower()]
        matches = self._filter_token_stats(matches, power, toughness, type_line, colors, text_hash)
        if matches.empty:
            return []
        return json.loads(matches.to_json(orient="records"))

    def get_default_token_printing_id(
        self, token_face_name: str, power: Optional[str] = None, toughness: Optional[str] = None,
        type_line: Optional[str] = None, colors: Optional[str] = None, text_hash: Optional[str] = None,
    ) -> Optional[str]:
        """Return the Scryfall ID of the default printing for a token/emblem identity.

        Mirrors `get_default_printing_id()`'s tie-break (highest score, then most
        recent `released_at`).
        """
        df = self._load_token_printings_df()
        if df is None:
            return None
        matches = df[(df["face_name"].str.lower() == token_face_name.lower()) & (df["is_default"])]
        matches = self._filter_token_stats(matches, power, toughness, type_line, colors, text_hash)
        if matches.empty:
            return None
        matches = matches.sort_values("released_at", ascending=False, na_position="last")
        return str(matches.iloc[0]["scryfall_id"])

    def get_token_printing_id_for_set(
        self, token_face_name: str, set_code: str, power: Optional[str] = None, toughness: Optional[str] = None,
        type_line: Optional[str] = None, colors: Optional[str] = None, text_hash: Optional[str] = None,
    ) -> Optional[str]:
        """Return the Scryfall ID of the token/emblem identity's printing within `set_code`.

        Mirrors `get_printing_id_for_set()`'s tie-break for real cards.
        """
        df = self._load_token_printings_df()
        if df is None:
            return None
        matches = df[
            (df["face_name"].str.lower() == token_face_name.lower())
            & (df["set"].str.upper() == set_code.upper())
        ]
        matches = self._filter_token_stats(matches, power, toughness, type_line, colors, text_hash)
        if matches.empty:
            return None
        matches = matches.sort_values(["score", "released_at"], ascending=[False, False], na_position="last")
        return str(matches.iloc[0]["scryfall_id"])

    def get_token_printing_image_path(self, token_face_name: str, scryfall_id: str, size: str = "normal") -> Path:
        """Build the on-disk path for a specific token/emblem printing's cached image."""
        return self.token_base_dir / sanitize_filename(token_face_name) / size / f"{scryfall_id}.jpg"

    def download_all_token_printings(
        self,
        mode: Optional[str] = None,
        sizes: Optional[list[str]] = None,
        progress_callback=None,
        max_rows: Optional[int] = None,
    ) -> dict[str, int]:
        """
        Download token/emblem images into the separate
        `card_files/images/tokens/{Token Name}/{size}/{scryfall_id}.jpg` tree,
        using the index built by `build_token_printings_index()`. Mirrors
        `download_all_printings()` but never touches the real-card image cache.

        Args:
            mode: 'default' (only the highest-scoring printing per face) or
                'full' (every paper printing). Defaults to IMAGE_CACHE_MODE
                env var (see `get_cache_mode()`).
            sizes: Image sizes to download (default: ['small', 'normal']).
            progress_callback: Optional callback(current, total, face_name).
            max_rows: Maximum printing rows to download (for testing).

        Returns:
            Dictionary with download statistics.

        Raises:
            FileNotFoundError: If the token printings index hasn't been built yet.
            ValueError: If `mode` is not a recognized value.
        """
        if not self.is_enabled():
            logger.info("Image caching disabled (CACHE_CARD_IMAGES=0)")
            return {"skipped": 0}

        if not self.token_printings_index_path.exists():
            raise FileNotFoundError(
                f"Token printings index not found: {self.token_printings_index_path}. "
                "Run build_token_printings_index() first."
            )

        resolved_mode = (mode or get_cache_mode()).strip().lower()
        if resolved_mode not in VALID_CACHE_MODES:
            raise ValueError(f"Invalid mode '{resolved_mode}'; expected one of {VALID_CACHE_MODES}")

        if sizes is None:
            sizes = IMAGE_SIZES

        import pandas as pd

        df = pd.read_parquet(self.token_printings_index_path)
        if resolved_mode == "default":
            df = df[df["is_default"]]
            df = df.sort_values("released_at", ascending=False, na_position="last")
            # Dedup by the full (face_name, power, toughness) identity, not
            # face_name alone -- same-named tokens with different stats (e.g.
            # "Elemental" 1/1 vs 2/2) are different identities and must each
            # keep their own default printing.
            df = df.drop_duplicates(subset=["face_name", "power", "toughness"], keep="first")

        if max_rows is not None:
            df = df.head(max_rows)

        stats = {"total": len(df), "downloaded": 0, "skipped": 0, "failed": 0}

        for i, row in enumerate(df.itertuples(index=False)):
            token_folder = self.token_base_dir / sanitize_filename(row.face_name)
            for size in sizes:
                image_url = row.image_url_small if size == "small" else row.image_url_normal
                if not image_url:
                    continue

                output_path = token_folder / size / f"{row.scryfall_id}.jpg"
                if output_path.exists():
                    stats["skipped"] += 1
                    continue

                if self._download_image(image_url, output_path):
                    stats["downloaded"] += 1
                else:
                    stats["failed"] += 1

            if progress_callback:
                progress_callback(i + 1, len(df), row.face_name)

        # Regenerate the token summary now (in this same background download
        # thread) rather than just invalidating it, so the next status poll
        # doesn't pay the directory-scan cost itself.
        token_summary_file = self.token_base_dir / "summary.json"
        if token_summary_file.exists():
            try:
                token_summary_file.unlink()
            except Exception as e:
                logger.warning(f"Could not delete token cache summary: {e}")
        self.token_cache_statistics()

        logger.info(f"Token/emblem printing-aware image download complete: {stats}")
        return stats

    def download_bulk_data(self, progress_callback=None) -> None:
        """
        Download latest Scryfall bulk data JSON.

        Args:
            progress_callback: Optional callback(bytes_downloaded, total_bytes)

        Raises:
            Exception: If download fails
        """
        logger.info("Downloading Scryfall bulk data...")
        self.bulk_data_path.parent.mkdir(parents=True, exist_ok=True)
        self.client.get_bulk_data(
            output_path=str(self.bulk_data_path),
            progress_callback=progress_callback,
        )
        logger.info("Bulk data download complete")

    def download_images(
        self,
        sizes: Optional[list[str]] = None,
        progress_callback=None,
        max_cards: Optional[int] = None,
    ) -> dict[str, int]:
        """
        Download card images from Scryfall CDN.

        Args:
            sizes: Image sizes to download (default: ['small', 'normal'])
            progress_callback: Optional callback(current, total, card_name)
            max_cards: Maximum cards to download (for testing)

        Returns:
            Dictionary with download statistics

        Raises:
            FileNotFoundError: If bulk data not available
        """
        if not self.is_enabled():
            logger.info("Image caching disabled (CACHE_CARD_IMAGES=0)")
            return {"skipped": 0}

        if sizes is None:
            sizes = IMAGE_SIZES

        logger.info(f"Starting image download for sizes: {sizes}")

        # Estimate total from parquet so the progress bar has a denominator.
        # This is a lightweight read (one column) and avoids loading bulk JSON twice.
        total_cards: int = 0
        try:
            import pandas as pd
            from code.path_util import get_processed_cards_path

            df_est = pd.read_parquet(get_processed_cards_path(), columns=["name"])
            total_cards = len(df_est)
            del df_est  # release immediately
        except Exception:
            pass  # progress will show 0 total if parquet unavailable

        if max_cards is not None:
            total_cards = min(max_cards, total_cards) if total_cards else max_cards

        stats = {
            "total": total_cards,
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
        }

        # Stream bulk JSON one card at a time — never loads entire file into RAM.
        card_index = 0
        for face_name, image_uris in self._stream_card_image_data():
            if max_cards is not None and card_index >= max_cards:
                break

            for size in sizes:
                image_url = image_uris.get(size)
                if not image_url:
                    continue

                safe_name = sanitize_filename(face_name)
                output_path = self.base_dir / size / f"{safe_name}.jpg"

                if output_path.exists():
                    stats["skipped"] += 1
                    continue

                if self._download_image(image_url, output_path):
                    stats["downloaded"] += 1
                else:
                    stats["failed"] += 1

            card_index += 1

            if progress_callback:
                progress_callback(card_index, total_cards, face_name)

        # Invalidate cached summary and in-memory index so new images are found immediately,
        # then regenerate the summary now rather than deferring the scan to the next status poll.
        self.invalidate_summary_cache()
        self.invalidate_index()
        self.cache_statistics()

        logger.info(f"Image download complete: {stats}")
        return stats

    def cache_statistics(self) -> dict[str, Any]:
        """
        Get statistics about cached images.
        
        Uses a cached summary.json file to avoid scanning thousands of files.
        Regenerates summary if it doesn't exist or is stale (based on WEB_AUTO_REFRESH_DAYS,
        default 7 days, matching the main card data staleness check).

        Returns:
            Dictionary with cache stats (count, size, etc.)
        """
        stats = {"enabled": self.is_enabled()}

        if not self.is_enabled():
            return stats

        summary_file = self.base_dir / "summary.json"
        
        # Get staleness threshold from environment (same as card data check)
        try:
            refresh_days = int(os.getenv('WEB_AUTO_REFRESH_DAYS', '7'))
        except Exception:
            refresh_days = 7
        
        if refresh_days <= 0:
            # Never consider stale
            refresh_seconds = float('inf')
        else:
            refresh_seconds = refresh_days * 24 * 60 * 60  # Convert days to seconds
        
        # Check if summary exists and is recent (less than refresh_seconds old)
        use_cached = False
        if summary_file.exists():
            try:
                import time
                file_age = time.time() - summary_file.stat().st_mtime
                if file_age < refresh_seconds:
                    use_cached = True
            except Exception:
                pass
        
        # Try to use cached summary
        if use_cached:
            try:
                import json
                with summary_file.open('r', encoding='utf-8') as f:
                    cached_stats = json.load(f)
                    stats.update(cached_stats)
                    return stats
            except Exception as e:
                logger.warning(f"Could not read cache summary: {e}")
        
        # Regenerate summary (counts files across both cache layouts). This
        # walks every per-card folder once for all sizes together, rather
        # than once per size, since Docker Desktop bind-mount filesystem
        # calls on Windows are slow enough that a second full tree walk is
        # noticeable at ~30k+ card folders.
        counts = {size: 0 for size in IMAGE_SIZES}

        # Legacy flat layout: card_files/images/{size}/*.jpg
        for size in IMAGE_SIZES:
            flat_dir = self.base_dir / size
            if flat_dir.exists():
                counts[size] += sum(1 for _ in flat_dir.glob("*.jpg"))

        # Per-card/per-printing layout: card_files/images/{Card Name}/{size}/*.jpg
        if self.base_dir.exists():
            for card_dir in self.base_dir.iterdir():
                if not card_dir.is_dir() or card_dir.name in IMAGE_SIZES:
                    continue
                for size in IMAGE_SIZES:
                    size_dir = card_dir / size
                    if size_dir.exists():
                        counts[size] += sum(1 for _ in size_dir.glob("*.jpg"))

        for size in IMAGE_SIZES:
            count = counts[size]
            # Estimate total size based on typical averages to avoid stat() calls
            # Small images: ~40 KB avg, Normal images: ~100 KB avg
            avg_size_kb = 40 if size == "small" else 100
            estimated_size_mb = (count * avg_size_kb) / 1024

            stats[size] = {
                "count": count,
                "size_mb": round(estimated_size_mb, 1),
            }
        
        # Save summary for next time
        try:
            import json
            with summary_file.open('w', encoding='utf-8') as f:
                json.dump({k: v for k, v in stats.items() if k != "enabled"}, f)
        except Exception as e:
            logger.warning(f"Could not write cache summary: {e}")

        return stats

    def token_cache_statistics(self) -> dict[str, Any]:
        """
        Get statistics about cached token/emblem images, mirroring
        `cache_statistics()` but scanning `token_base_dir`'s per-token-name
        subfolders (`{Token Name}/{size}/*.jpg`) instead of the real-card
        flat `{size}/*.jpg` layout.

        Returns:
            Dictionary with cache stats (count, size, etc.)
        """
        stats = {"enabled": self.is_enabled()}

        if not self.is_enabled():
            return stats

        summary_file = self.token_base_dir / "summary.json"

        try:
            refresh_days = int(os.getenv('WEB_AUTO_REFRESH_DAYS', '7'))
        except Exception:
            refresh_days = 7

        if refresh_days <= 0:
            refresh_seconds = float('inf')
        else:
            refresh_seconds = refresh_days * 24 * 60 * 60

        use_cached = False
        if summary_file.exists():
            try:
                file_age = time.time() - summary_file.stat().st_mtime
                if file_age < refresh_seconds:
                    use_cached = True
            except Exception:
                pass

        if use_cached:
            try:
                with summary_file.open('r', encoding='utf-8') as f:
                    cached_stats = json.load(f)
                    stats.update(cached_stats)
                    return stats
            except Exception as e:
                logger.warning(f"Could not read token cache summary: {e}")

        for size in IMAGE_SIZES:
            count = 0
            if self.token_base_dir.exists():
                for token_dir in self.token_base_dir.iterdir():
                    if not token_dir.is_dir():
                        continue
                    size_dir = token_dir / size
                    if size_dir.exists():
                        count += sum(1 for _ in size_dir.glob("*.jpg"))
            avg_size_kb = 40 if size == "small" else 100
            estimated_size_mb = (count * avg_size_kb) / 1024
            stats[size] = {"count": count, "size_mb": round(estimated_size_mb, 1)}

        try:
            self.token_base_dir.mkdir(parents=True, exist_ok=True)
            with summary_file.open('w', encoding='utf-8') as f:
                json.dump({k: v for k, v in stats.items() if k != "enabled"}, f)
        except Exception as e:
            logger.warning(f"Could not write token cache summary: {e}")

        return stats

    def invalidate_index(self) -> None:
        """Reset the in-memory image index so it is rebuilt on the next access."""
        self._image_index.clear()
        self._index_built = False
        logger.debug("Invalidated in-memory image index")

    def invalidate_summary_cache(self) -> None:
        """Delete the cached summary file to force regeneration on next call."""
        if not self.is_enabled():
            return
        
        summary_file = self.base_dir / "summary.json"
        if summary_file.exists():
            try:
                summary_file.unlink()
                logger.debug("Invalidated cache summary file")
            except Exception as e:
                logger.warning(f"Could not delete cache summary: {e}")


def main():
    """CLI entry point for image caching."""
    import argparse

    parser = argparse.ArgumentParser(description="Card image cache management")
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download images from Scryfall",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show cache statistics",
    )
    parser.add_argument(
        "--max-cards",
        type=int,
        help="Maximum cards to download (for testing)",
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        default=IMAGE_SIZES,
        choices=IMAGE_SIZES,
        help="Image sizes to download",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download of bulk data even if recent",
    )
    parser.add_argument(
        "--build-printings-index",
        action="store_true",
        help="Build/refresh card_printings.parquet (every paper printing's metadata)",
    )
    parser.add_argument(
        "--backup-cache",
        action="store_true",
        help="Move the existing card_files/images/ cache aside before a fresh redownload",
    )
    parser.add_argument(
        "--download-printings",
        action="store_true",
        help="Download images into the new per-card/per-printing layout (requires --build-printings-index first)",
    )
    parser.add_argument(
        "--mode",
        choices=VALID_CACHE_MODES,
        default=None,
        help="Download mode for --download-printings: 'default' (one printing per card) or 'full' (every printing). Defaults to IMAGE_CACHE_MODE env var.",
    )

    args = parser.parse_args()

    # On Windows, stdout/stderr default to the console codepage (cp1252)
    # when redirected to a file, which raises UnicodeEncodeError on the
    # rare card name containing a character outside that codepage (e.g.
    # combining/modifier letters used by a handful of real card names).
    # A crash here would otherwise kill a multi-hour download partway
    # through -- force UTF-8 with a safe fallback instead.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    cache = ImageCache()

    if args.backup_cache:
        backup_path = cache.backup_existing_cache()
        if backup_path:
            print(f"Backed up existing cache to {backup_path}")
        else:
            print("No existing cache directory to back up")

    if args.build_printings_index:
        print("Building printings index (this reads the full bulk data file)...")
        count = cache.build_printings_index()
        print(f"Printings index written: {count} rows -> {cache.printings_index_path}")

    if args.download_printings:
        if not cache.is_enabled():
            print("Image caching is disabled. Set CACHE_CARD_IMAGES=1 to enable.")
            return

        def printing_progress(current, total, card_name):
            pct = (current / total) * 100 if total else 0
            print(f"  Progress: {current}/{total} ({pct:.1f}%) - {card_name}", end="\r")

        stats = cache.download_all_printings(mode=args.mode, sizes=args.sizes, progress_callback=printing_progress)
        print("\n\nDownload complete:")
        print(f"  Total: {stats['total']}")
        print(f"  Downloaded: {stats['downloaded']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Failed: {stats['failed']}")

    if args.stats:
        stats = cache.cache_statistics()
        print("\nCache Statistics:")
        print(f"  Enabled: {stats['enabled']}")
        if stats["enabled"]:
            for size in IMAGE_SIZES:
                if size in stats:
                    print(
                        f"  {size.capitalize()}: {stats[size]['count']} images "
                        f"({stats[size]['size_mb']:.1f} MB)"
                    )

    elif args.download:
        if not cache.is_enabled():
            print("Image caching is disabled. Set CACHE_CARD_IMAGES=1 to enable.")
            return

        # Check if bulk data already exists and is recent (within 24 hours)
        bulk_data_exists = cache.bulk_data_path.exists()
        bulk_data_age_hours = None
        
        if bulk_data_exists:
            import time
            age_seconds = time.time() - cache.bulk_data_path.stat().st_mtime
            bulk_data_age_hours = age_seconds / 3600
            print(f"Bulk data file exists (age: {bulk_data_age_hours:.1f} hours)")
        
        # Download bulk data if missing, old, or forced
        if not bulk_data_exists or bulk_data_age_hours > 24 or args.force:
            print("Downloading Scryfall bulk data...")

            def bulk_progress(downloaded, total):
                if total > 0:
                    pct = (downloaded / total) * 100
                    print(f"  Progress: {downloaded / 1024 / 1024:.1f} MB / "
                          f"{total / 1024 / 1024:.1f} MB ({pct:.1f}%)", end="\r")

            cache.download_bulk_data(progress_callback=bulk_progress)
            print("\nBulk data downloaded successfully")
        else:
            print("Bulk data is recent, skipping download (use --force to re-download)")

        # Download images
        print(f"\nDownloading card images (sizes: {', '.join(args.sizes)})...")

        def image_progress(current, total, card_name):
            pct = (current / total) * 100
            print(f"  Progress: {current}/{total} ({pct:.1f}%) - {card_name}", end="\r")

        stats = cache.download_images(
            sizes=args.sizes,
            progress_callback=image_progress,
            max_cards=args.max_cards,
        )
        print("\n\nDownload complete:")
        print(f"  Total: {stats['total']}")
        print(f"  Downloaded: {stats['downloaded']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Failed: {stats['failed']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
