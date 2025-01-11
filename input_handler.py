"""Input handling and validation module for MTG Python Deckbuilder."""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple, Union

import inquirer.prompt  # type: ignore
from settings import (
    COLORS, COLOR_ABBREVIATIONS, DEFAULT_MAX_CARD_PRICE,
    DEFAULT_MAX_DECK_PRICE, DEFAULT_THEME_TAGS, MONO_COLOR_MAP,
    DUAL_COLOR_MAP, TRI_COLOR_MAP, OTHER_COLOR_MAP
)

from exceptions import (
    CommanderColorError,
    CommanderStatsError,
    CommanderTagError,
    CommanderThemeError,
    CommanderTypeError,
    DeckBuilderError,
    EmptyInputError,
    InvalidNumberError,
    InvalidQuestionTypeError,
    MaxAttemptsError,
    PriceError,
    PriceLimitError,
    PriceValidationError
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class InputHandler:
    """Handles user input operations with validation and error handling.
    
    This class provides methods for collecting and validating different types
    of user input including text, numbers, confirmations, and choices.
    
    Attributes:
        max_attempts (int): Maximum number of retry attempts for invalid input
        default_text (str): Default value for text input
        default_number (float): Default value for number input
        default_confirm (bool): Default value for confirmation input
    """
    
    def __init__(
        self,
        max_attempts: int = 3,
        default_text: str = '',
        default_number: float = 0.0,
        default_confirm: bool = True
    ):
        """Initialize input handler with configuration.
        
        Args:
            max_attempts: Maximum number of retry attempts
            default_text: Default value for text input
            default_number: Default value for number input
            default_confirm: Default value for confirmation input
        """
        self.max_attempts = max_attempts
        self.default_text = default_text
        self.default_number = default_number
        self.default_confirm = default_confirm
    
    def validate_text(self, result: str) -> bool:
        """Validate text input is not empty.
        
        Args:
            result: Text input to validate
            
        Returns:
            True if text is not empty after stripping whitespace
            
        Raises:
            EmptyInputError: If input is empty or whitespace only
        """
        if not result or not result.strip():
            raise EmptyInputError()
        return True
    
    def validate_number(self, result: str) -> float:
        """Validate and convert string input to float.
        
        Args:
            result: Number input to validate
            
        Returns:
            Converted float value
            
        Raises:
            InvalidNumberError: If input cannot be converted to float
        """
        try:
            return float(result)
        except (ValueError, TypeError):
            raise InvalidNumberError(result)

    def validate_price(self, result: str) -> Tuple[float, bool]:
        """Validate and convert price input to float with format checking.
        
        Args:
            result: Price input to validate
            
        Returns:
            Tuple of (price value, is_unlimited flag)
            
        Raises:
            PriceValidationError: If price format is invalid
        """
        result = result.strip().lower()
        
        # Check for unlimited budget
        if result in ['unlimited', 'any']:
            return (float('inf'), True)
            
        # Remove currency symbol if present
        if result.startswith('$'):
            result = result[1:]
            
        try:
            price = float(result)
            if price < 0:
                raise PriceValidationError('Price cannot be negative')
            return (price, False)
        except ValueError:
            raise PriceValidationError(f"Invalid price format: '{result}'")
            
    def validate_price_threshold(self, price: float, threshold: float = DEFAULT_MAX_CARD_PRICE) -> bool:
        """Validate price against maximum threshold.
        
        Args:
            price: Price value to check
            threshold: Maximum allowed price (default from settings)
            
        Returns:
            True if price is within threshold
            
        Raises:
            PriceLimitError: If price exceeds threshold
        """
        if price > threshold and price != float('inf'):
            raise PriceLimitError('Card', price, threshold)
        return True
    
    def validate_confirm(self, result: bool) -> bool:
        """Validate confirmation input.
        
        Args:
            result: Boolean confirmation input
            
        Returns:
            The boolean input value
        """
        return bool(result)
    
    def questionnaire(
        self,
        question_type: str,
        message: str = '',
        default_value: Any = None,
        choices_list: List[str] = None
    ) -> Union[str, float, bool]:
        """Present questions to user and handle input validation.
        
        Args:
            question_type: Type of question ('Text', 'Number', 'Confirm', 'Choice')
            message: Question message to display
            default_value: Default value for the question
            choices_list: List of choices for Choice type questions
            
        Returns:
            Validated user input of appropriate type
            
        Raises:
            InvalidQuestionTypeError: If question_type is not supported
            MaxAttemptsError: If maximum retry attempts are exceeded
        """
        attempts = 0
        
        while attempts < self.max_attempts:
            try:
                if question_type == 'Text':
                    question = [
                        inquirer.Text(
                            'text',
                            message=message or 'Enter text',
                            default=default_value or self.default_text
                        )
                    ]
                    result = inquirer.prompt(question)['text']
                    if self.validate_text(result):
                        return result
                
                elif question_type == 'Price':
                    question = [
                        inquirer.Text(
                            'price',
                            message=message or 'Enter price (or "unlimited")',
                            default=str(default_value or DEFAULT_MAX_CARD_PRICE)
                        )
                    ]
                    result = inquirer.prompt(question)['price']
                    price, is_unlimited = self.validate_price(result)
                    if not is_unlimited:
                        self.validate_price_threshold(price)
                    return price
                elif question_type == 'Number':
                    question = [
                        inquirer.Text(
                            'number',
                            message=message or 'Enter number',
                            default=str(default_value or self.default_number)
                        )
                    ]
                    result = inquirer.prompt(question)['number']
                    return self.validate_number(result)
                
                elif question_type == 'Confirm':
                    question = [
                        inquirer.Confirm(
                            'confirm',
                            message=message or 'Confirm?',
                            default=default_value if default_value is not None else self.default_confirm
                        )
                    ]
                    result = inquirer.prompt(question)['confirm']
                    return self.validate_confirm(result)
                
                elif question_type == 'Choice':
                    if not choices_list:
                        raise ValueError("Choices list cannot be empty for Choice type")
                    question = [
                        inquirer.List(
                            'selection',
                            message=message or 'Select an option',
                            choices=choices_list,
                            carousel=True
                        )
                    ]
                    return inquirer.prompt(question)['selection']
                
                else:
                    raise InvalidQuestionTypeError(question_type)
                
            except DeckBuilderError as e:
                logging.warning(f"Input validation failed: {e}")
                attempts += 1
                if attempts >= self.max_attempts:
                    raise MaxAttemptsError(
                        self.max_attempts,
                        question_type.lower(),
                        {"last_error": str(e)}
                    )
            
            except Exception as e:
                logging.error(f"Unexpected error in questionnaire: {e}")
                raise
        
        raise MaxAttemptsError(self.max_attempts, question_type.lower())

    def validate_commander_type(self, type_line: str) -> str:
        """Validate commander type line requirements.

        Args:
            type_line: Commander's type line to validate

        Returns:
            Validated type line

        Raises:
            CommanderTypeError: If type line validation fails
        """
        if not type_line:
            raise CommanderTypeError("Type line cannot be empty")

        type_line = type_line.strip()

        # Check for legendary creature requirement
        if not ('Legendary' in type_line and 'Creature' in type_line):
            # Check for 'can be your commander' text
            if 'can be your commander' not in type_line.lower():
                raise CommanderTypeError(
                    "Commander must be a legendary creature or have 'can be your commander' text"
                )

        return type_line

    def validate_commander_stats(self, stat_name: str, value: str) -> int:
        """Validate commander numerical statistics.

        Args:
            stat_name: Name of the stat (power, toughness, mana value)
            value: Value to validate

        Returns:
            Validated integer value

        Raises:
            CommanderStatsError: If stat validation fails
        """
        try:
            stat_value = int(value)
            if stat_value < 0 and stat_name != 'power':
                raise CommanderStatsError(f"{stat_name} cannot be negative")
            return stat_value
        except ValueError:
            raise CommanderStatsError(
                f"Invalid {stat_name} value: '{value}'. Must be a number."
            )

    def _normalize_color_string(self, colors: str) -> str:
        """Helper method to standardize color string format.

        Args:
            colors: Raw color string to normalize

        Returns:
            Normalized color string
        """
        if not colors:
            return 'colorless'

        # Remove whitespace and sort color symbols
        colors = colors.strip().upper()
        color_symbols = [c for c in colors if c in 'WUBRG']
        return ', '.join(sorted(color_symbols))

    def _validate_color_combination(self, colors: str) -> bool:
        """Helper method to validate color combinations.

        Args:
            colors: Normalized color string to validate

        Returns:
            True if valid, False otherwise
        """
        if colors == 'colorless':
            return True

        # Check against valid combinations from settings
        return (colors in COLOR_ABBREVIATIONS or
                any(colors in combo for combo in [MONO_COLOR_MAP, DUAL_COLOR_MAP,
                                                TRI_COLOR_MAP, OTHER_COLOR_MAP]))

    def validate_color_identity(self, colors: str) -> str:
        """Validate commander color identity using settings constants.

        Args:
            colors: Color identity string to validate

        Returns:
            Validated color identity string

        Raises:
            CommanderColorError: If color validation fails
        """
        # Normalize the color string
        normalized = self._normalize_color_string(colors)

        # Validate the combination
        if not self._validate_color_combination(normalized):
            raise CommanderColorError(
                f"Invalid color identity: '{colors}'. Must be a valid color combination."
            )

        return normalized

    def validate_commander_colors(self, colors: str) -> str:
        """Validate commander color identity.

        Args:
            colors: Color identity string to validate

        Returns:
            Validated color identity string

        Raises:
            CommanderColorError: If color validation fails
        """
        try:
            return self.validate_color_identity(colors)
        except CommanderColorError as e:
            logging.error(f"Color validation failed: {e}")
            raise
    def validate_commander_tags(self, tags: List[str]) -> List[str]:
        """Validate commander theme tags.

        Args:
            tags: List of theme tags to validate

        Returns:
            Validated list of theme tags

        Raises:
            CommanderTagError: If tag validation fails
        """
        if not isinstance(tags, list):
            raise CommanderTagError("Tags must be provided as a list")

        validated_tags = []
        for tag in tags:
            if not isinstance(tag, str):
                raise CommanderTagError(f"Invalid tag type: {type(tag)}. Must be string.")
            tag = tag.strip()
            if tag:
                validated_tags.append(tag)

        return validated_tags

    def validate_commander_themes(self, themes: List[str]) -> List[str]:
        """Validate commander themes.

        Args:
            themes: List of themes to validate

        Returns:
            Validated list of themes

        Raises:
            CommanderThemeError: If theme validation fails
        """
        if not isinstance(themes, list):
            raise CommanderThemeError("Themes must be provided as a list")

        validated_themes = []
        for theme in themes:
            if not isinstance(theme, str):
                raise CommanderThemeError(f"Invalid theme type: {type(theme)}. Must be string.")
            theme = theme.strip()
            if theme and theme in DEFAULT_THEME_TAGS:
                validated_themes.append(theme)
            else:
                raise CommanderThemeError(f"Invalid theme: '{theme}'")

        return validated_themes