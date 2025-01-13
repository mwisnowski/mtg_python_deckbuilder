"""Custom exceptions for MTG Python Deckbuilder setup operations."""

class MTGSetupError(Exception):
    """Base exception class for MTG setup-related errors."""
    pass

class CSVFileNotFoundError(MTGSetupError):
    """Exception raised when a required CSV file is not found.
    
    This exception is raised when attempting to access or process a CSV file
    that does not exist in the expected location.
    
    Args:
        message: Explanation of the error
        filename: Name of the missing CSV file
    """
    def __init__(self, message: str, filename: str) -> None:
        self.filename = filename
        super().__init__(f"{message}: {filename}")

class MTGJSONDownloadError(MTGSetupError):
    """Exception raised when downloading data from MTGJSON fails.
    
    This exception is raised when there are issues downloading card data
    from the MTGJSON API, such as network errors or API failures.
    
    Args:
        message: Explanation of the error
        url: The URL that failed to download
        status_code: HTTP status code if available
    """
    def __init__(self, message: str, url: str, status_code: int = None) -> None:
        self.url = url
        self.status_code = status_code
        status_info = f" (Status: {status_code})" if status_code else ""
        super().__init__(f"{message}: {url}{status_info}")

class DataFrameProcessingError(MTGSetupError):
    """Exception raised when DataFrame operations fail during setup.
    
    This exception is raised when there are issues processing card data
    in pandas DataFrames, such as filtering, sorting, or transformation errors.
    
    Args:
        message: Explanation of the error
        operation: The DataFrame operation that failed (e.g., 'color_filtering', 'commander_processing')
        details: Additional error details
    
    Examples:
        >>> raise DataFrameProcessingError(
        ...     "Invalid color identity",
        ...     "color_filtering",
        ...     "Color 'P' is not a valid MTG color"
        ... )
    """
    def __init__(self, message: str, operation: str, details: str = None) -> None:
        self.operation = operation
        self.details = details
        error_info = f" - {details}" if details else ""
        super().__init__(f"{message} during {operation}{error_info}")


class ColorFilterError(MTGSetupError):
    """Exception raised when color-specific filtering operations fail.
    
    This exception is raised when there are issues filtering cards by color,
    such as invalid color specifications or color identity processing errors.
    
    Args:
        message: Explanation of the error
        color: The color value that caused the error
        details: Additional error details
    
    Examples:
        >>> raise ColorFilterError(
        ...     "Invalid color specification",
        ...     "Purple",
        ...     "Color must be one of: W, U, B, R, G, or C"
        ... )
    """
    def __init__(self, message: str, color: str, details: str = None) -> None:
        self.color = color
        self.details = details
        error_info = f" - {details}" if details else ""
        super().__init__(f"{message} for color '{color}'{error_info}")


class CommanderValidationError(MTGSetupError):
    """Exception raised when commander validation fails.
    
    This exception is raised when there are issues validating commander cards,
    such as non-legendary creatures, color identity mismatches, or banned cards.
    
    Args:
        message: Explanation of the error
        validation_type: Type of validation that failed (e.g., 'legendary_check', 'color_identity', 'banned_set')
        details: Additional error details
    
    Examples:
        >>> raise CommanderValidationError(
        ...     "Card must be legendary",
        ...     "legendary_check",
        ...     "Lightning Bolt is not a legendary creature"
        ... )
        
        >>> raise CommanderValidationError(
        ...     "Commander color identity mismatch",
        ...     "color_identity",
        ...     "Omnath, Locus of Creation cannot be used in Golgari deck"
        ... )
        
        >>> raise CommanderValidationError(
        ...     "Commander banned in format",
        ...     "banned_set",
        ...     "Golos, Tireless Pilgrim is banned in Commander"
        ... )
    """
    def __init__(self, message: str, validation_type: str, details: str = None) -> None:
        self.validation_type = validation_type
        self.details = details
        error_info = f" - {details}" if details else ""
        super().__init__(f"{message} [{validation_type}]{error_info}")