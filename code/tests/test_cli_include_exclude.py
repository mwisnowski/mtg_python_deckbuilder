"""
Test CLI include/exclude functionality (M4: CLI Parity).
"""

import pytest
import subprocess
import json
import os
import tempfile
from pathlib import Path


class TestCLIIncludeExclude:
    """Test CLI include/exclude argument parsing and functionality."""

    def test_cli_argument_parsing(self):
        """Test that CLI arguments are properly parsed."""
        # Test help output includes new arguments
        result = subprocess.run(
            ['python', 'code/headless_runner.py', '--help'],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent
        )
        
        assert result.returncode == 0
        help_text = result.stdout
        assert '--include-cards' in help_text
        assert '--exclude-cards' in help_text
        assert '--enforcement-mode' in help_text
        assert '--allow-illegal' in help_text
        assert '--fuzzy-matching' in help_text
        assert 'semicolons' in help_text  # Check for comma warning

    def test_cli_dry_run_with_include_exclude(self):
        """Test dry run output includes include/exclude configuration."""
        result = subprocess.run([
            'python', 'code/headless_runner.py',
            '--commander', 'Krenko, Mob Boss',
            '--include-cards', 'Sol Ring;Lightning Bolt',
            '--exclude-cards', 'Chaos Orb',
            '--enforcement-mode', 'strict',
            '--dry-run'
        ], capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)
        
        assert result.returncode == 0
        
        # Parse the JSON output
        config = json.loads(result.stdout)
        
        assert config['command_name'] == 'Krenko, Mob Boss'
        assert config['include_cards'] == ['Sol Ring', 'Lightning Bolt']
        assert config['exclude_cards'] == ['Chaos Orb']
        assert config['enforcement_mode'] == 'strict'

    def test_cli_semicolon_parsing(self):
        """Test semicolon separation for card names with commas."""
        result = subprocess.run([
            'python', 'code/headless_runner.py',
            '--include-cards', 'Krenko, Mob Boss;Jace, the Mind Sculptor',
            '--exclude-cards', 'Teferi, Hero of Dominaria',
            '--dry-run'
        ], capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)
        
        assert result.returncode == 0
        
        config = json.loads(result.stdout)
        assert config['include_cards'] == ['Krenko, Mob Boss', 'Jace, the Mind Sculptor']
        assert config['exclude_cards'] == ['Teferi, Hero of Dominaria']

    def test_cli_comma_parsing_simple_names(self):
        """Test comma separation for simple card names without commas."""
        result = subprocess.run([
            'python', 'code/headless_runner.py',
            '--include-cards', 'Sol Ring,Lightning Bolt,Counterspell',
            '--exclude-cards', 'Island,Mountain',
            '--dry-run'
        ], capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)
        
        assert result.returncode == 0
        
        config = json.loads(result.stdout)
        assert config['include_cards'] == ['Sol Ring', 'Lightning Bolt', 'Counterspell']
        assert config['exclude_cards'] == ['Island', 'Mountain']

    def test_cli_json_priority(self):
        """Test that CLI arguments override JSON config values."""
        # Create a temporary JSON config
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'commander': 'Atraxa, Praetors\' Voice',
                'include_cards': ['Doubling Season'],
                'exclude_cards': ['Winter Orb'],
                'enforcement_mode': 'warn'
            }, f, indent=2)
            temp_config = f.name
        
        try:
            result = subprocess.run([
                'python', 'code/headless_runner.py',
                '--config', temp_config,
                '--include-cards', 'Sol Ring',  # Override JSON
                '--enforcement-mode', 'strict',  # Override JSON
                '--dry-run'
            ], capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)
            
            assert result.returncode == 0
            
            config = json.loads(result.stdout)
            # CLI should override JSON
            assert config['include_cards'] == ['Sol Ring']  # CLI override
            assert config['exclude_cards'] == ['Winter Orb']  # From JSON (no CLI override)
            assert config['enforcement_mode'] == 'strict'  # CLI override
            
        finally:
            os.unlink(temp_config)

    def test_cli_empty_values(self):
        """Test handling of empty/missing include/exclude values."""
        result = subprocess.run([
            'python', 'code/headless_runner.py',
            '--commander', 'Krenko, Mob Boss',
            '--dry-run'
        ], capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)
        
        assert result.returncode == 0
        
        config = json.loads(result.stdout)
        assert config['include_cards'] == []
        assert config['exclude_cards'] == []
        assert config['enforcement_mode'] == 'warn'  # Default
        assert config['allow_illegal'] is False  # Default
        assert config['fuzzy_matching'] is True  # Default


if __name__ == '__main__':
    pytest.main([__file__])
