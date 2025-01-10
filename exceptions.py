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