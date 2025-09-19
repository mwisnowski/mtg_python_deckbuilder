import os
import sys

if 'code' not in sys.path:
    sys.path.insert(0, 'code')

os.environ['EDITORIAL_INCLUDE_FALLBACK_SUMMARY'] = '1'

from scripts.build_theme_catalog import main  # noqa: E402

if __name__ == '__main__':
    main()