# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['.venv\\gui.py'],
    pathex=[],
    binaries=[],
    datas=[('.venv\\mode.ini', '.'), ('.venv\\target_config.ini', '.'), ('withholding-icon-transparent.ico', '_internal')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DCM to STL Autoconverter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['withholding-icon-transparent.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DCM to STL Autoconverter',
)
