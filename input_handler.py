"""Input handling and validation module for MTG Python Deckbuilder."""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Union

import inquirer.prompt # type: ignore

from exceptions import (
    DeckBuilderError,
    EmptyInputError,
    InvalidNumberError,
    InvalidQuestionTypeError,
    MaxAttemptsError
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