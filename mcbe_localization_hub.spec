# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['mcbe_localization_hub.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=['openai', 'httpx'],
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
    a.binaries,
    a.datas,
    [],
    name='mcbe_localization_hub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='C:/Users/DEVILE~1/AppData/Local/Temp/be4d8a20-d38d-451f-b663-8a9a79dfad5e',
    icon=['assets/app_icon.ico'],
)
