"""Input validation and handling for MTG Python Deckbuilder.

This module provides the InputHandler class which encapsulates all input validation
and handling logic. It supports different types of input validation including text,
numbers, confirmations, and multiple choice questions.
"""

from typing import Any, List, Optional, Union
import inquirer
import logging
import os

from exceptions import InputValidationError
from settings import INPUT_VALIDATION, QUESTION_TYPES

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/input_handlers.log', mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class InputHandler:
    """Handles input validation and user interaction.
    
    This class provides methods for validating different types of user input
    and handling user interaction through questionnaires. It uses constants
    from settings.py for validation messages and configuration.
    """
    
    def validate_text(self, result: str) -> bool:
        """Validate text input is not empty.
        
        Args:
            result: Text input to validate
            
        Returns:
            bool: True if text is not empty after stripping whitespace
            
        Raises:
            InputValidationError: If text validation fails
        """
        try:
            if not result or not result.strip():
                raise InputValidationError(
                    INPUT_VALIDATION['default_text_message'],
                    'text',
                    'Input cannot be empty'
                )
            return True
        except Exception as e:
            raise InputValidationError(
                str(e),
                'text',
                'Unexpected error during text validation'
            )

    def validate_number(self, result: str) -> Optional[float]:
        """Validate and convert string input to float.
        
        Args:
            result: Number input to validate
            
        Returns:
            float | None: Converted float value or None if invalid
            
        Raises:
            InputValidationError: If number validation fails
        """
        try:
            if not result:
                raise InputValidationError(
                    INPUT_VALIDATION['default_number_message'],
                    'number',
                    'Input cannot be empty'
                )
            return float(result)
        except ValueError:
            raise InputValidationError(
                INPUT_VALIDATION['default_number_message'],
                'number',
                'Input must be a valid number'
            )
        except Exception as e:
            raise InputValidationError(
                str(e),
                'number',
                'Unexpected error during number validation'
            )

    def validate_confirm(self, result: Any) -> bool:
        """Validate confirmation input.
        
        Args:
            result: Confirmation input to validate
            
        Returns:
            bool: True for positive confirmation, False otherwise
            
        Raises:
            InputValidationError: If confirmation validation fails
        """
        try:
            if isinstance(result, bool):
                return result
            if isinstance(result, str):
                result = result.lower().strip()
                if result in ('y', 'yes', 'true', '1'):
                    return True
                if result in ('n', 'no', 'false', '0'):
                    return False
            raise InputValidationError(
                INPUT_VALIDATION['default_confirm_message'],
                'confirm',
                'Invalid confirmation response'
            )
        except InputValidationError:
            raise
        except Exception as e:
            raise InputValidationError(
                str(e),
                'confirm',
                'Unexpected error during confirmation validation'
            )

    def questionnaire(
        self,
        question_type: str,
        default_value: Union[str, bool, float] = '',
        choices_list: List[str] = []
    ) -> Union[str, bool, float]:
        """Present questions to user and validate input.
        
        Args:
            question_type: Type of question ('Text', 'Number', 'Confirm', 'Choice')
            default_value: Default value for the question
            choices_list: List of choices for Choice type questions
            
        Returns:
            Union[str, bool, float]: Validated user input
            
        Raises:
            InputValidationError: If input validation fails
            ValueError: If question type is not supported
        """
        if question_type not in QUESTION_TYPES:
            raise ValueError(f"Unsupported question type: {question_type}")

        attempts = 0
        while attempts < INPUT_VALIDATION['max_attempts']:
            try:
                if question_type == 'Text':
                    question = [inquirer.Text('text')]
                    result = inquirer.prompt(question)['text']
                    if self.validate_text(result):
                        return result

                elif question_type == 'Number':
                    question = [inquirer.Text('number', default=str(default_value))]
                    result = inquirer.prompt(question)['number']
                    validated = self.validate_number(result)
                    if validated is not None:
                        return validated

                elif question_type == 'Confirm':
                    question = [inquirer.Confirm('confirm', default=default_value)]
                    result = inquirer.prompt(question)['confirm']
                    return self.validate_confirm(result)

                elif question_type == 'Choice':
                    if not choices_list:
                        raise InputValidationError(
                            INPUT_VALIDATION['default_choice_message'],
                            'choice',
                            'No choices provided'
                        )
                    question = [
                        inquirer.List('selection',
                            choices=choices_list,
                            carousel=True)
                    ]
                    return inquirer.prompt(question)['selection']

            except InputValidationError as e:
                attempts += 1
                if attempts >= INPUT_VALIDATION['max_attempts']:
                    raise InputValidationError(
                        "Maximum input attempts reached",
                        question_type,
                        str(e)
                    )
                logger.warning(f"Invalid input ({attempts}/{INPUT_VALIDATION['max_attempts']}): {str(e)}")

            except Exception as e:
                raise InputValidationError(
                    str(e),
                    question_type,
                    'Unexpected error during questionnaire'
                )

        raise InputValidationError(
            "Maximum input attempts reached",
            question_type,
            "Failed to get valid input"
        )