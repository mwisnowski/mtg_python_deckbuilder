# MTG Python Deckbuilder

A command-line tool for building and analyzing Magic: The Gathering decks with advanced features for the Commander/EDH format.

## Features

- **Deck Building**: Create and manage Commander/EDH decks with intelligent card suggestions and theme detection
- **Card Information**: Look up detailed card information with fuzzy name matching
- **CSV File Tagging**: Automatically tag cards with themes and strategies
- **Commander Support**: Comprehensive support for Commander/EDH format rules and restrictions
- **Theme Detection**: Identify and suggest cards based on deck themes and strategies
- **Color Identity**: Filter cards based on Commander color identity rules
- **Price Checking**: Check card prices and stay within budget constraints
- **Data Management**: Efficient storage and retrieval of card data using CSV files

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/mtg_python_deckbuilder.git
   cd mtg_python_deckbuilder
   ```

2. Install dependencies using pip:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the application using:
```bash
python main.py
```

The main menu provides the following options:
- **Setup**: Initialize the card database and perform initial configuration
- **Build a Deck**: Create a new Commander deck with theme detection
- **Get Card Info**: Look up detailed information about specific cards
- **Tag CSV Files**: Process and tag card data files

## Dependencies

Core dependencies:
- pandas >= 1.5.0
- inquirer >= 3.1.3
- typing-extensions >= 4.5.0
- fuzzywuzzy
- python-Levenshtein
- ipython

Development dependencies:
- mypy >= 1.3.0
- pandas-stubs >= 2.0.0
- types-inquirer >= 3.1.3

## Development Setup

1. Install development dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run type checks with mypy:
   ```bash
   mypy .
   ```

## Project Structure

- `main.py`: Entry point and CLI interface
- `card_info.py`: Card information lookup functionality
- `tagger.py`: Card tagging and theme detection
- `setup.py`: Database setup and initialization
- `settings.py`: Configuration and constants
- `type_definitions.py`: Custom type definitions

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.