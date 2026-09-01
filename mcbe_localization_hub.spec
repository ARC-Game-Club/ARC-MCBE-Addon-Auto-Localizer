# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

rapidocr_datas, rapidocr_binaries, rapidocr_hiddenimports = collect_all('rapidocr')
onnx_datas, onnx_binaries, onnx_hiddenimports = collect_all('onnxruntime')

a = Analysis(
    ['mcbe_localization_hub.py'],
    pathex=[],
    binaries=rapidocr_binaries + onnx_binaries,
    datas=[('assets', 'assets')] + rapidocr_datas + onnx_datas,
    hiddenimports=['openai', 'httpx', 'numpy'] + rapidocr_hiddenimports + onnx_hiddenimports,
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
    icon=['assets/app_icon.ico'],
)
