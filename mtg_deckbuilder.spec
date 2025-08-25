# PyInstaller spec to build mtg-deckbuilder reliably with code package
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = collect_submodules('code')

a = Analysis(
    ['code/main.py'],
    pathex=['.','code'],
    binaries=[],
    datas=[('csv_files/*', 'csv_files'), ('deck_files/*', 'deck_files'), ('logs/*', 'logs'), ('config/*', 'config')],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='mtg-deckbuilder',
    debug=False,
    strip=False,
    upx=True,
    console=True,
)