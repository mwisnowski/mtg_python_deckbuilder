"""Custom exceptions for the MTG Python Deckbuilder application."""

class DeckBuilderError(Exception):
    """Base exception class for deck builder errors.
    
    Attributes:
        code (str): Error code for identifying the error type
        message (str): Descriptive error message
        details (dict): Additional error context and details
    """
    
    def __init__(self, message: str, code: str = "DECK_ERR", details: dict | None = None):
        """Initialize the base deck builder error.
        
        Args:
            message: Human-readable error description
            code: Error code for identification and handling
            details: Additional context about the error
        """
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self) -> str:
        """Format the error message with code and details."""
        error_msg = f"[{self.code}] {self.message}"
        if self.details:
            error_msg += f"\nDetails: {self.details}"
        return error_msg

class MTGSetupError(DeckBuilderError):
    """Base exception class for MTG setup-related errors.
    
    This exception serves as the base for all setup-related errors in the deck builder,
    including file operations, data processing, and validation during setup.
    """
    
    def __init__(self, message: str, code: str = "SETUP_ERR", details: dict | None = None):
        """Initialize the base setup error.
        
        Args:
            message: Human-readable error description
            code: Error code for identification and handling
            details: Additional context about the error
        """
        super().__init__(message, code=code, details=details)

class CSVFileNotFoundError(MTGSetupError):
    """Exception raised when a required CSV file is not found.
    
    This exception is raised when attempting to access or process a CSV file
    that does not exist in the expected location.
    """
    
    def __init__(self, filename: str, details: dict | None = None):
        """Initialize CSV file not found error.
        
        Args:
            filename: Name of the missing CSV file
            details: Additional context about the missing file
        """
        message = f"Required CSV file not found: '{filename}'"
        super().__init__(message, code="CSV_MISSING", details=details)

class MTGJSONDownloadError(MTGSetupError):
    """Exception raised when downloading data from MTGJSON fails.
    
    This exception is raised when there are issues downloading card data
    from the MTGJSON API, such as network errors or API failures.
    """
    
    def __init__(self, url: str, status_code: int | None = None, details: dict | None = None):
        """Initialize MTGJSON download error.
        
        Args:
            url: The URL that failed to download
            status_code: HTTP status code if available
            details: Additional context about the download failure
        """
        status_info = f" (Status: {status_code})" if status_code else ""
        message = f"Failed to download from MTGJSON: {url}{status_info}"
        super().__init__(message, code="MTGJSON_ERR", details=details)

# Input Handler Exceptions
class EmptyInputError(DeckBuilderError):
    """Raised when text input validation fails due to empty or whitespace-only input.
    
    This exception is used by the validate_text method when checking user input.
    """
    
    def __init__(self, field_name: str = "input", details: dict | None = None):
        """Initialize empty input error.
        
        Args:
            field_name: Name of the input field that was empty
            details: Additional context about the validation failure
        """
        message = f"Empty or whitespace-only {field_name} is not allowed"
        super().__init__(message, code="EMPTY_INPUT", details=details)

class InvalidNumberError(DeckBuilderError):
    """Raised when number input validation fails.
    
    This exception is used by the validate_number method when checking numeric input.
    """
    
    def __init__(self, value: str, details: dict | None = None):
        """Initialize invalid number error.
        
        Args:
            value: The invalid input value
            details: Additional context about the validation failure
        """
        message = f"Invalid number format: '{value}'"
        super().__init__(message, code="INVALID_NUM", details=details)

class InvalidQuestionTypeError(DeckBuilderError):
    """Raised when an unsupported question type is used in the questionnaire method.
    
    This exception is raised when the questionnaire method receives an unknown question type.
    """
    
    def __init__(self, question_type: str, details: dict | None = None):
        """Initialize invalid question type error.
        
        Args:
            question_type: The unsupported question type
            details: Additional context about the error
        """
        message = f"Unsupported question type: '{question_type}'"
        super().__init__(message, code="INVALID_QTYPE", details=details)

class MaxAttemptsError(DeckBuilderError):
    """Raised when maximum input attempts are exceeded.
    
    This exception is used when user input validation fails multiple times.
    """
    
    def __init__(self, max_attempts: int, input_type: str = "input", details: dict | None = None):
        """Initialize maximum attempts error.
        
        Args:
            max_attempts: Maximum number of attempts allowed
            input_type: Type of input that failed validation
            details: Additional context about the attempts
        """
        message = f"Maximum {input_type} attempts ({max_attempts}) exceeded"
        super().__init__(message, code="MAX_ATTEMPTS", details=details)

# CSV Exceptions
class CSVError(DeckBuilderError):
    """Base exception class for CSV-related errors.
    
    This exception serves as the base for all CSV-related errors in the deck builder,
    including file reading, processing, validation, and timeout issues.
    
    Attributes:
        code (str): Error code for identifying the error type
        message (str): Descriptive error message
        details (dict): Additional error context and details
    """
    
    def __init__(self, message: str, code: str = "CSV_ERR", details: dict | None = None):
        """Initialize the base CSV error.
        
        Args:
            message: Human-readable error description
            code: Error code for identification and handling
            details: Additional context about the error
        """
        super().__init__(message, code=code, details=details)

class CSVReadError(CSVError):
    """Raised when there are issues reading CSV files.
    
    This exception is used when CSV files cannot be opened, read, or parsed.
    """
    
    def __init__(self, filename: str, details: dict | None = None):
        """Initialize CSV read error.
        
        Args:
            filename: Name of the CSV file that failed to read
            details: Additional context about the read failure
        """
        message = f"Failed to read CSV file: '{filename}'"
        super().__init__(message, code="CSV_READ", details=details)

class CSVProcessingError(CSVError):
    """Base class for CSV and DataFrame processing errors.
    
    This exception is used when operations fail during data processing,
    including batch operations and transformations.
    """
    
    def __init__(self, message: str, operation_context: dict | None = None, details: dict | None = None):
        """Initialize processing error with context.
        
        Args:
            message: Descriptive error message
            operation_context: Details about the failed operation
            details: Additional error context
        """
        if operation_context:
            details = details or {}
            details['operation_context'] = operation_context
        super().__init__(message, code="CSV_PROC", details=details)

class DataFrameProcessingError(CSVProcessingError):
    """Raised when DataFrame batch operations fail.
    
    This exception provides detailed context about batch processing failures
    including operation state and progress information.
    """
    
    def __init__(self, operation: str, batch_state: dict, processed_count: int, total_count: int, details: dict | None = None):
        """Initialize DataFrame processing error.
        
        Args:
            operation: Name of the operation that failed
            batch_state: Current state of batch processing
            processed_count: Number of items processed
            total_count: Total number of items to process
            details: Additional error context
        """
        message = f"DataFrame batch operation '{operation}' failed after processing {processed_count}/{total_count} items"
        operation_context = {
            'operation': operation,
            'batch_state': batch_state,
            'processed_count': processed_count,
            'total_count': total_count
        }
        super().__init__(message, operation_context, details)

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

class CSVValidationError(CSVError):
    """Base class for CSV and DataFrame validation errors.
    
    This exception is used when data fails validation checks, including field validation,
    data type validation, and data consistency validation.
    """
    
    def __init__(self, message: str, validation_context: dict | None = None, details: dict | None = None):
        """Initialize validation error with context.
        
        Args:
            message: Descriptive error message
            validation_context: Specific validation failure details
            details: Additional error context
        """
        if validation_context:
            details = details or {}
            details['validation_context'] = validation_context
        super().__init__(message, code="CSV_VALID", details=details)

class DataFrameValidationError(CSVValidationError):
    """Raised when DataFrame validation fails.
    
    This exception provides detailed context about validation failures including
    rule violations, invalid values, and data type mismatches.
    """
    
    def __init__(self, field: str, validation_rules: dict, invalid_data: dict | None = None, details: dict | None = None):
        """Initialize DataFrame validation error.
        
        Args:
            field: Name of the field that failed validation
            validation_rules: Rules that were violated
            invalid_data: The invalid data that caused the failure
            details: Additional error context
        """
        message = f"DataFrame validation failed for field '{field}'"
        validation_context = {
            'field': field,
            'rules': validation_rules,
            'invalid_data': invalid_data or {}
        }
        super().__init__(message, validation_context, details)

class EmptyDataFrameError(CSVError):
    """Raised when a DataFrame is unexpectedly empty.
    
    This exception is used when a DataFrame operation requires non-empty data
    but receives an empty DataFrame.
    """
    
    def __init__(self, operation: str, details: dict | None = None):
        """Initialize empty DataFrame error.
        
        Args:
            operation: Name of the operation that requires non-empty data
            details: Additional context about the empty DataFrame
        """
        message = f"Empty DataFrame encountered during: '{operation}'"
        super().__init__(message, code="CSV_EMPTY", details=details)

class CSVTimeoutError(CSVError):
    """Base class for CSV and DataFrame timeout errors.
    
    This exception is used when operations exceed their timeout thresholds.
    """
    
    def __init__(self, message: str, timeout_context: dict | None = None, details: dict | None = None):
        """Initialize timeout error with context.
        
        Args:
            message: Descriptive error message
            timeout_context: Details about the timeout
            details: Additional error context
        """
        if timeout_context:
            details = details or {}
            details['timeout_context'] = timeout_context
        super().__init__(message, code="CSV_TIMEOUT", details=details)

class DataFrameTimeoutError(CSVTimeoutError):
    """Raised when DataFrame operations timeout.
    
    This exception provides detailed context about operation timeouts
    including operation type and duration information.
    """
    
    def __init__(self, operation: str, timeout: float, elapsed: float, operation_state: dict | None = None, details: dict | None = None):
        """Initialize DataFrame timeout error.
        
        Args:
            operation: Name of the operation that timed out
            timeout: Timeout threshold in seconds
            elapsed: Actual time elapsed in seconds
            operation_state: State of the operation when timeout occurred
            details: Additional error context
        """
        message = f"DataFrame operation '{operation}' timed out after {elapsed:.1f}s (threshold: {timeout}s)"
        timeout_context = {
            'operation': operation,
            'timeout_threshold': timeout,
            'elapsed_time': elapsed,
            'operation_state': operation_state or {}
        }
        super().__init__(message, timeout_context, details)

# For PriceCheck/Scrython functions
class PriceError(DeckBuilderError):
    """Base exception class for price-related errors.
    
    This exception serves as the base for all price-related errors in the deck builder,
    including API issues, validation errors, and price limit violations.
    
    Attributes:
        code (str): Error code for identifying the error type
        message (str): Descriptive error message
        details (dict): Additional error context and details
    """
    
    def __init__(self, message: str, code: str = "PRICE_ERR", details: dict | None = None):
        """Initialize the base price error.
        
        Args:
            message: Human-readable error description
            code: Error code for identification and handling
            details: Additional context about the error
        """
        super().__init__(message, code=code, details=details)

class PriceAPIError(PriceError):
    """Raised when there are issues with the Scryfall API price lookup.
    
    This exception is used when the price API request fails, returns invalid data,
    or encounters other API-related issues.
    """
    
    def __init__(self, card_name: str, details: dict | None = None):
        """Initialize price API error.
        
        Args:
            card_name: Name of the card that failed price lookup
            details: Additional context about the API failure
        """
        message = f"Failed to fetch price data for '{card_name}' from Scryfall API"
        super().__init__(message, code="PRICE_API", details=details)

class PriceLimitError(PriceError):
    """Raised when a card or deck price exceeds the specified limit.
    
    This exception is used when price thresholds are violated during deck building.
    """
    
    def __init__(self, card_name: str, price: float, limit: float, details: dict | None = None):
        """Initialize price limit error.
        
        Args:
            card_name: Name of the card exceeding the price limit
            price: Actual price of the card
            limit: Maximum allowed price
            details: Additional context about the price limit violation
        """
        message = f"Price of '{card_name}' (${price:.2f}) exceeds limit of ${limit:.2f}"
        super().__init__(message, code="PRICE_LIMIT", details=details)

class PriceTimeoutError(PriceError):
    """Raised when a price lookup request times out.
    
    This exception is used when the Scryfall API request exceeds the timeout threshold.
    """
    
    def __init__(self, card_name: str, timeout: float, details: dict | None = None):
        """Initialize price timeout error.
        
        Args:
            card_name: Name of the card that timed out
            timeout: Timeout threshold in seconds
            details: Additional context about the timeout
        """
        message = f"Price lookup for '{card_name}' timed out after {timeout} seconds"
        super().__init__(message, code="PRICE_TIMEOUT", details=details)

class PriceValidationError(PriceError):
    """Raised when price data fails validation.
    
    This exception is used when received price data is invalid, malformed,
    or cannot be properly parsed.
    """
    
    def __init__(self, card_name: str, price_data: str, details: dict | None = None):
        """Initialize price validation error.
        
        Args:
            card_name: Name of the card with invalid price data
            price_data: The invalid price data received
            details: Additional context about the validation failure
        """
        message = f"Invalid price data for '{card_name}': {price_data}"
        super().__init__(message, code="PRICE_INVALID", details=details)

# Commander Exceptions
class CommanderLoadError(DeckBuilderError):
    """Raised when there are issues loading commander data from CSV.
    
    This exception is used when the commander CSV file cannot be loaded,
    is missing required columns, or contains invalid data.
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize commander load error.
        
        Args:
            message: Description of the loading failure
            details: Additional context about the error
        """
        super().__init__(message, code="CMD_LOAD", details=details)

class CommanderSelectionError(DeckBuilderError):
    """Raised when there are issues with the commander selection process.
    
    This exception is used when the commander selection process fails,
    such as no matches found or ambiguous matches.
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize commander selection error.
        
        Args:
            message: Description of the selection failure
            details: Additional context about the error
        """
        super().__init__(message, code="CMD_SELECT", details=details)

class CommanderValidationError(DeckBuilderError):
    """Raised when commander data fails validation.
    
    This exception is used when the selected commander's data is invalid,
    missing required fields, or contains inconsistent information.
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize commander validation error.
        
        Args:
            message: Description of the validation failure
            details: Additional context about the error
        """
        super().__init__(message, code="CMD_VALID", details=details)

class CommanderTypeError(CommanderValidationError):
    """Raised when commander type validation fails.
    
    This exception is used when a commander fails the legendary creature requirement
    or has an invalid creature type.
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize commander type error.
        
        Args:
            message: Description of the type validation failure
            details: Additional context about the error
        """
        super().__init__(message, code="CMD_TYPE_ERR", details=details)

class CommanderStatsError(CommanderValidationError):
    """Raised when commander stats validation fails.
    
    This exception is used when a commander's power, toughness, or mana value
    fails validation requirements.
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize commander stats error.
        
        Args:
            message: Description of the stats validation failure
            details: Additional context about the error
        """
        super().__init__(message, code="CMD_STATS_ERR", details=details)

class CommanderColorError(CommanderValidationError):
    """Raised when commander color identity validation fails.
    
    This exception is used when a commander's color identity is invalid
    or incompatible with deck requirements.
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize commander color error.
        
        Args:
            message: Description of the color validation failure
            details: Additional context about the error
        """
        super().__init__(message, code="CMD_COLOR_ERR", details=details)

class CommanderTagError(CommanderValidationError):
    """Raised when commander theme tag validation fails.
    
    This exception is used when a commander's theme tags are invalid
    or incompatible with deck requirements.
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize commander tag error.
        
        Args:
            message: Description of the tag validation failure
            details: Additional context about the error
        """
        super().__init__(message, code="CMD_TAG_ERR", details=details)

class CommanderThemeError(CommanderValidationError):
    """Raised when commander theme validation fails.
    
    This exception is used when a commander's themes are invalid
    or incompatible with deck requirements.
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize commander theme error.
        
        Args:
            message: Description of the theme validation failure
            details: Additional context about the error
        """
        super().__init__(message, code="CMD_THEME_ERR", details=details)

class CommanderMoveError(DeckBuilderError):
    """Raised when there are issues moving the commander to the top of the library.
    
    This exception is used when the commander_to_top() method encounters problems
    such as commander not found in library, invalid deck state, or other issues
    preventing the commander from being moved to the top position.
    
    Examples:
        >>> raise CommanderMoveError(
        ...     "Commander not found in library",
        ...     {"commander_name": "Atraxa, Praetors' Voice"}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize commander move error.
        
        Args:
            message: Description of the move operation failure
            details: Additional context about the error
        """
        super().__init__(message, code="CMD_MOVE_ERR", details=details)

class LibraryOrganizationError(DeckBuilderError):
    """Base exception class for library organization errors.
    
    This exception serves as the base for all errors related to organizing
    and managing the card library, including card type counting and validation.
    
    Attributes:
        code (str): Error code for identifying the error type
        message (str): Descriptive error message
        details (dict): Additional error context and details
    """
    
    def __init__(self, message: str, code: str = "LIB_ORG_ERR", details: dict | None = None):
        """Initialize the library organization error.
        
        Args:
            message: Human-readable error description
            code: Error code for identification and handling
            details: Additional context about the error
        """
        super().__init__(message, code=code, details=details)

class LibrarySortError(LibraryOrganizationError):
    """Raised when there are issues sorting the card library.
    
    This exception is used when the sort_library() method encounters problems
    organizing cards by type and name, such as invalid sort orders or
    card type categorization errors.
    
    Examples:
        >>> raise LibrarySortError(
        ...     "Invalid card type sort order",
        ...     "Card type 'Unknown' not in sort order list"
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize library sort error.
        
        Args:
            message: Description of the sorting failure
            details: Additional context about the error
        """
        if details:
            details = details or {}
            details['sort_error'] = True
        super().__init__(message, code="LIB_SORT_ERR", details=details)

class DuplicateCardError(LibraryOrganizationError):
    """Raised when there are issues processing duplicate cards in the library.
    
    This exception is used when the concatenate_duplicates() method encounters problems
    processing duplicate cards, such as invalid card names, missing data, or
    inconsistencies in duplicate card information.
    
    Examples:
        >>> raise DuplicateCardError(
        ...     "Failed to process duplicate cards",
        ...     "Sol Ring",
        ...     {"duplicate_count": 3}
        ... )
    """
    
    def __init__(self, message: str, card_name: str | None = None, details: dict | None = None):
        """Initialize duplicate card error.
        
        Args:
            message: Description of the duplicate processing failure
            card_name: Name of the card causing the duplication error
            details: Additional context about the error
        """
        if card_name:
            details = details or {}
            details['card_name'] = card_name
        super().__init__(message, code="DUPLICATE_CARD", details=details)

class CardTypeCountError(LibraryOrganizationError):
    """Raised when there are issues counting cards of specific types.
    
    This exception is used when card type counting operations fail or
    produce invalid results during library organization.
    
    Examples:
        >>> raise CardTypeCountError(
        ...     "Invalid creature count",
        ...     "creature",
        ...     {"expected": 30, "actual": 15}
        ... )
    """
    
    def __init__(self, message: str, card_type: str, details: dict | None = None):
        """Initialize card type count error.
        
        Args:
            message: Description of the counting failure
            card_type: The type of card that caused the counting error
            details: Additional context about the error
        """
        if card_type:
            details = details or {}
            details['card_type'] = card_type
        super().__init__(message, code="CARD_TYPE_COUNT", details=details)

class ThemeError(DeckBuilderError):
    """Base exception class for theme-related errors.
    
    This exception serves as the base for all theme-related errors in the deck builder,
    including theme selection, validation, and weight calculation issues.
    
    Attributes:
        code (str): Error code for identifying the error type
        message (str): Descriptive error message
        details (dict): Additional error context and details
    """
    
    def __init__(self, message: str, code: str = "THEME_ERR", details: dict | None = None):
        """Initialize the base theme error.
        
        Args:
            message: Human-readable error description
            code: Error code for identification and handling
            details: Additional context about the error
        """
        super().__init__(message, code=code, details=details)

class ThemeSelectionError(ThemeError):
    """Raised when theme selection fails or is invalid.
    
    This exception is used when an invalid theme is selected or when
    the theme selection process is canceled by the user.
    
    Examples:
        >>> raise ThemeSelectionError(
        ...     "Invalid theme selected",
        ...     "artifacts",
        ...     {"available_themes": ["tokens", "lifegain", "counters"]}
        ... )
    """
    
    def __init__(self, message: str, selected_theme: str | None = None, details: dict | None = None):
        """Initialize theme selection error.
        
        Args:
            message: Description of the selection failure
            selected_theme: The invalid theme that was selected (if any)
            details: Additional context about the error
        """
        if selected_theme:
            details = details or {}
            details['selected_theme'] = selected_theme
        super().__init__(message, code="THEME_SELECT", details=details)

class ThemeWeightError(ThemeError):
    """Raised when theme weight calculation fails.
    
    This exception is used when there are errors in calculating or validating
    theme weights during the theme selection process.
    """
    
    def __init__(self, message: str, theme: str | None = None, details: dict | None = None):
        """Initialize theme weight error.
        
        Args:
            message: Description of the weight calculation failure
            theme: The theme that caused the weight calculation error
            details: Additional context about the error
        """
        if theme:
            details = details or {}
            details['theme'] = theme
        super().__init__(message, code="THEME_WEIGHT", details=details)

class IdealDeterminationError(DeckBuilderError):
    """Raised when there are issues determining deck composition ideals.
    
    This exception is used when the determine_ideals() method encounters problems
    calculating or validating deck composition ratios and requirements.
    
    Examples:
        >>> raise IdealDeterminationError(
        ...     "Invalid land ratio calculation",
        ...     {"calculated_ratio": 0.1, "min_allowed": 0.3}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize ideal determination error.
        
        Args:
            message: Description of the ideal calculation failure
            details: Additional context about the error
        """
        super().__init__(message, code="IDEAL_ERR", details=details)

class PriceConfigurationError(DeckBuilderError):
    """Raised when there are issues configuring price settings.
    
    This exception is used when price-related configuration in determine_ideals()
    is invalid or cannot be properly applied.
    
    Examples:
        >>> raise PriceConfigurationError(
        ...     "Invalid budget allocation",
        ...     {"total_budget": 100, "min_card_price": 200}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize price configuration error.
        
        Args:
            message: Description of the price configuration failure
            details: Additional context about the error
        """
        super().__init__(message, code="PRICE_CONFIG_ERR", details=details)

class BasicLandError(DeckBuilderError):
    """Base exception class for basic land related errors.
    
    This exception serves as the base for all basic land related errors in the deck builder,
    including land distribution, snow-covered lands, and colorless deck handling.
    
    Attributes:
        code (str): Error code for identifying the error type
        message (str): Descriptive error message
        details (dict): Additional error context and details
    """
    
    def __init__(self, message: str, code: str = "BASIC_LAND_ERR", details: dict | None = None):
        """Initialize the basic land error.
        
        Args:
            message: Human-readable error description
            code: Error code for identification and handling
        """
        super().__init__(message, code=code, details=details)

class BasicLandCountError(BasicLandError):
    """Raised when there are issues with counting basic lands.
    
    This exception is used when basic land counting operations fail or
    produce unexpected results during deck validation or analysis.
    
    Examples:
        >>> raise BasicLandCountError(
        ...     "Failed to count basic lands in deck",
        ...     {"expected_count": 35, "actual_count": 0}
        ... )
        
        >>> raise BasicLandCountError(
        ...     "Invalid basic land count for color distribution",
        ...     {"color": "U", "count": -1}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize basic land count error.
        
        Args:
            message: Description of the counting operation failure
            details: Additional context about the error
        """
        super().__init__(message, code="BASIC_LAND_COUNT_ERR", details=details)

class StapleLandError(DeckBuilderError):
    """Raised when there are issues adding staple lands.
    ```
    This exception is used when there are problems adding staple lands
    to the deck, such as invalid land types, missing lands, or
    incompatible color requirements.
    
    Examples:
        >>> raise StapleLandError(
        ...     "Failed to add required shock lands",
        ...     {"missing_lands": ["Steam Vents", "Breeding Pool"]}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize staple land error.
        
        Args:
            message: Description of the staple land operation failure
            details: Additional context about the error
        """
        super().__init__(
            message,
            code="STAPLE_LAND_ERR",
            details=details
        )

class LandDistributionError(BasicLandError):
    """Raised when there are issues with basic land distribution.
    
    This exception is used when there are problems distributing basic lands
    across colors, such as invalid color ratios or unsupported color combinations.
    
    Examples:
        >>> raise LandDistributionError(
        ...     "Invalid land distribution for colorless deck",
        ...     {"colors": [], "requested_lands": 40}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize land distribution error.
        
        Args:
            message: Description of the land distribution failure
            details: Additional context about the error
        """
        super().__init__(message, code="LAND_DIST_ERR", details=details)

class FetchLandError(DeckBuilderError):
    """Base exception class for fetch land-related errors.
    
    This exception serves as the base for all fetch land-related errors in the deck builder,
    including validation errors, selection errors, and fetch land processing issues.
    
    Attributes:
        code (str): Error code for identifying the error type
        message (str): Descriptive error message
        details (dict): Additional error context and details
    """
    
    def __init__(self, message: str, code: str = "FETCH_ERR", details: dict | None = None):
        """Initialize the base fetch land error.
        
        Args:
            message: Human-readable error description
            code: Error code for identification and handling
            details: Additional context about the error
        """
        super().__init__(message, code=code, details=details)
    
class KindredLandError(DeckBuilderError):
    """Base exception class for Kindred land-related errors.
    
    This exception serves as the base for all Kindred land-related errors in the deck builder,
    including validation errors, selection errors, and Kindred land processing issues.
    
    Attributes:
        code (str): Error code for identifying the error type
        message (str): Descriptive error message
        details (dict): Additional error context and details
    """
    
    def __init__(self, message: str, code: str = "KINDRED_ERR", details: dict | None = None):
        """Initialize the base Kindred land error.
        
        Args:
            message: Human-readable error description
            code: Error code for identification and handling
            details: Additional context about the error
        """
        super().__init__(message, code=code, details=details)

class KindredLandValidationError(KindredLandError):
    """Raised when Kindred land validation fails.
    
    This exception is used when there are issues validating Kindred land inputs,
    such as invalid land types, unsupported creature types, or color identity mismatches.
    
    Examples:
        >>> raise KindredLandValidationError(
        ...     "Invalid Kindred land type",
        ...     {"land_type": "Non-Kindred Land", "creature_type": "Elf"}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize Kindred land validation error.
        
        Args:
            message: Description of the validation failure
            details: Additional context about the error
        """
        super().__init__(message, code="KINDRED_VALID_ERR", details=details)

class KindredLandSelectionError(KindredLandError):
    """Raised when Kindred land selection fails.
    
    This exception is used when there are issues selecting appropriate Kindred lands,
    such as no valid lands found, creature type mismatches, or price constraints.
    
    Examples:
        >>> raise KindredLandSelectionError(
        ...     "No valid Kindred lands found for creature type",
        ...     {"creature_type": "Dragon", "attempted_lands": ["Cavern of Souls"]}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize Kindred land selection error.
        
        Args:
            message: Description of the selection failure
            details: Additional context about the error
        """
        super().__init__(message, code="KINDRED_SELECT_ERR", details=details)

class FetchLandValidationError(FetchLandError):
    """Raised when fetch land validation fails.
    
    This exception is used when there are issues validating fetch land inputs,
    such as invalid fetch count, unsupported colors, or invalid fetch land types.
    
    Examples:
        >>> raise FetchLandValidationError(
        ...     "Invalid fetch land count",
        ...     {"requested": 10, "maximum": 9}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize fetch land validation error.
        
        Args:
            message: Description of the validation failure
            details: Additional context about the error
        """
        super().__init__(message, code="FETCH_VALID_ERR", details=details)

class FetchLandSelectionError(FetchLandError):
    """Raised when fetch land selection fails.
    
    This exception is used when there are issues selecting appropriate fetch lands,
    such as no valid fetches found, color identity mismatches, or price constraints.
    
    Examples:
        >>> raise FetchLandSelectionError(
        ...     "No valid fetch lands found for color identity",
        ...     {"colors": ["W", "U"], "attempted_fetches": ["Flooded Strand", "Polluted Delta"]}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize fetch land selection error.
        
        Args:
            message: Description of the selection failure
            details: Additional context about the error
        """
        super().__init__(message, code="FETCH_SELECT_ERR", details=details)

class DualLandError(DeckBuilderError):
    """Base exception class for dual land-related errors.
    
    This exception serves as the base for all dual land-related errors in the deck builder,
    including validation errors, selection errors, and dual land processing issues.
    
    Attributes:
        code (str): Error code for identifying the error type
        message (str): Descriptive error message
        details (dict): Additional error context and details
    """
    
    def __init__(self, message: str, code: str = "DUAL_ERR", details: dict | None = None):
        """Initialize the base dual land error.
        
        Args:
            message: Human-readable error description
            code: Error code for identification and handling
            details: Additional context about the error
        """
        super().__init__(message, code=code, details=details)

class DualLandValidationError(DualLandError):
    """Raised when dual land validation fails.
    
    This exception is used when there are issues validating dual land inputs,
    such as invalid dual land types, color identity mismatches, or budget constraints.
    
    Examples:
        >>> raise DualLandValidationError(
        ...     "Invalid dual land type",
        ...     {"land_type": "Not a dual land", "colors": ["W", "U"]}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize dual land validation error.
        
        Args:
            message: Description of the validation failure
            details: Additional context about the error
        """
        super().__init__(message, code="DUAL_VALID_ERR", details=details)

class DualLandSelectionError(DualLandError):
    """Raised when dual land selection fails.
    
    This exception is used when there are issues selecting appropriate dual lands,
    such as no valid duals found, color identity mismatches, or price constraints.
    
    Examples:
        >>> raise DualLandSelectionError(
        ...     "No valid dual lands found for color identity",
        ...     {"colors": ["W", "U"], "attempted_duals": ["Tundra", "Hallowed Fountain"]}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize dual land selection error.
        
        Args:
            message: Description of the selection failure
            details: Additional context about the error
        """
        super().__init__(message, code="DUAL_SELECT_ERR", details=details)

class TripleLandError(DeckBuilderError):
    """Base exception class for triple land-related errors.
    
    This exception serves as the base for all triple land-related errors in the deck builder,
    including validation errors, selection errors, and triple land processing issues.
    
    Attributes:
        code (str): Error code for identifying the error type
        message (str): Descriptive error message
        details (dict): Additional error context and details
    """
    
    def __init__(self, message: str, code: str = "TRIPLE_ERR", details: dict | None = None):
        """Initialize the base triple land error.
        
        Args:
            message: Human-readable error description
            code: Error code for identification and handling
            details: Additional context about the error
        """
        super().__init__(message, code=code, details=details)

class TripleLandValidationError(TripleLandError):
    """Raised when triple land validation fails.
    
    This exception is used when there are issues validating triple land inputs,
    such as invalid triple land types, color identity mismatches, or budget constraints.
    
    Examples:
        >>> raise TripleLandValidationError(
        ...     "Invalid triple land type",
        ...     {"land_type": "Not a triple land", "colors": ["W", "U", "B"]}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize triple land validation error.
        
        Args:
            message: Description of the validation failure
            details: Additional context about the error
        """
        super().__init__(message, code="TRIPLE_VALID_ERR", details=details)

class TripleLandSelectionError(TripleLandError):
    """Raised when triple land selection fails.
    
    This exception is used when there are issues selecting appropriate triple lands,
    such as no valid triples found, color identity mismatches, or price constraints.
    
    Examples:
        >>> raise TripleLandSelectionError(
        ...     "No valid triple lands found for color identity",
        ...     {"colors": ["W", "U", "B"], "attempted_triples": ["Arcane Sanctum", "Seaside Citadel"]}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize triple land selection error.
        
        Args:
            message: Description of the selection failure
            details: Additional context about the error
        """
        super().__init__(message, code="TRIPLE_SELECT_ERR", details=details)

class MiscLandSelectionError(DeckBuilderError):
    """Raised when miscellaneous land selection fails.
    
    This exception is used when there are issues selecting appropriate miscellaneous lands,
    such as insufficient lands in the pool, invalid land types, or selection criteria failures.
    
    Examples:
        >>> raise MiscLandSelectionError(
        ...     "Insufficient lands in pool for selection",
        ...     {"available_count": 50, "required_count": 100}
        ... )
        
        >>> raise MiscLandSelectionError(
        ...     "Invalid land type in selection pool",
        ...     {"invalid_lands": ["Not a Land", "Also Not a Land"]}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize miscellaneous land selection error.
        
        Args:
            message: Description of the selection failure
            details: Additional context about the error
        """
        super().__init__(
            message,
            code="MISC_LAND_ERR",
            details=details
        )

class LandRemovalError(DeckBuilderError):
    """Raised when there are issues removing lands from the deck.
    
    This exception is used when the land removal process encounters problems,
    such as no removable lands available, invalid land selection criteria,
    or when removing lands would violate deck construction rules.
    
    Examples:
        >>> raise LandRemovalError(
        ...     "No removable lands found in deck",
        ...     {"deck_size": 100, "current_lands": 36, "minimum_lands": 36}
        ... )
        
        >>> raise LandRemovalError(
        ...     "Cannot remove required basic lands",
        ...     {"land_type": "Basic Forest", "current_count": 5, "minimum_required": 5}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize land removal error.
        
        Args:
            message: Description of the land removal failure
            details: Additional context about the error
        """
        super().__init__(
            message,
            code="LAND_REMOVE_ERR",
            details=details
        )

class ManaPipError(DeckBuilderError):
    """Raised when there are issues analyzing mana pips in the deck.
    
    This exception is used when there are problems analyzing or calculating
    mana pips in the deck, such as invalid mana costs, calculation errors,
    or inconsistencies in pip distribution analysis.
    
    Examples:
        >>> raise ManaPipError(
        ...     "Invalid mana cost format",
        ...     {"card_name": "Invalid Card", "mana_cost": "Not Valid"}
        ... )
        
        >>> raise ManaPipError(
        ...     "Error calculating color pip distribution",
        ...     {"colors": ["W", "U"], "pip_counts": "invalid"}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize mana pip error.
        
        Args:
            message: Description of the mana pip analysis failure
            details: Additional context about the error
        """
        super().__init__(
            message,
            code="MANA_PIP_ERR",
            details=details
        )

class ThemeTagError(DeckBuilderError):
    """Raised when there are issues processing theme tags.
    
    This exception is used when there are problems processing or validating theme tags,
    such as invalid tag formats, missing required tags, or tag validation failures.
    
    Examples:
        >>> raise ThemeTagError(
        ...     "Invalid theme tag format",
        ...     {"tag": "invalid#tag", "expected_format": "theme:subtheme"}
        ... )
        
        >>> raise ThemeTagError(
        ...     "Missing required theme tags",
        ...     {"card_name": "Example Card", "required_tags": ["theme:tribal", "theme:synergy"]}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize theme tag error.
        
        Args:
            message: Description of the theme tag processing failure
            details: Additional context about the error
        """
        super().__init__(
            message,
            code="THEME_TAG_ERR",
            details=details
        )

class ThemeWeightingError(DeckBuilderError):
    """Raised when there are issues with theme-based card weighting.
    
    This exception is used when there are problems calculating or validating
    theme weights, such as invalid weight values, calculation errors, or
    inconsistencies in theme weight distribution.
    
    Examples:
        >>> raise ThemeWeightingError(
        ...     "Invalid theme weight value",
        ...     {"theme": "tribal", "weight": -1, "valid_range": "0-100"}
        ... )
        
        >>> raise ThemeWeightingError(
        ...     "Theme weight calculation error",
        ...     {"theme": "artifacts", "error": "Division by zero in weight normalization"}
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize theme weighting error.
        
        Args:
            message: Description of the theme weighting failure
            details: Additional context about the error
        """
        super().__init__(
            message,
            code="THEME_WEIGHT_ERR",
            details=details
        )

class ThemePoolError(DeckBuilderError):
    """Raised when there are issues with the theme card pool.
    
    This exception is used when there are problems creating or managing the theme
    card pool, such as empty pools, insufficient cards, or invalid pool configurations.
    
    Examples:
        >>> raise ThemePoolError(
        ...     "Empty theme card pool",
        ...     {"theme": "spellslinger", "required_cards": 30}
        ... )
        
        >>> raise ThemePoolError(
        ...     "Insufficient cards in theme pool",
        ...     {
        ...         "theme": "artifacts",
        ...         "available_cards": 15,
        ...         "required_cards": 25
        ...     }
        ... )
        
        >>> raise ThemePoolError(
        ...     "Invalid card pool configuration",
        ...     {
        ...         "theme": "tribal",
        ...         "creature_type": "Dragon",
        ...         "error": "No cards match creature type"
        ...     }
        ... )
    """
    
    def __init__(self, message: str, details: dict | None = None):
        """Initialize theme pool error.
        
        Args:
            message: Description of the theme pool failure
            details: Additional context about the error
        """
        super().__init__(
            message,
            code="THEME_POOL_ERR",
            details=details
        )