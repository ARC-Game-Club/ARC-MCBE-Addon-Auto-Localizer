# -*- mode: python ; coding: utf-8 -*-
import glob
import zipfile
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

rapidocr_datas, rapidocr_binaries, rapidocr_hiddenimports = collect_all('rapidocr')
onnx_datas, onnx_binaries, onnx_hiddenimports = collect_all('onnxruntime')

# flet 桌面客户端必须以 flet-windows.zip 归档内置（运行时 ensure_client_cached 只认
# 归档，不认解包目录），否则干净机器首启会联网下载。zip 从本机 ~/.flet 客户端缓存生成。
_client_dirs = sorted(glob.glob(str(Path.home() / '.flet' / 'client' / 'flet-desktop-full-*')))
if not _client_dirs:
    raise SystemExit(
        '未找到 flet 客户端缓存：先用 .venv 运行一次 mcbe_localization_hub.py '
        '下载客户端，再执行打包'
    )
_client_flet = Path(_client_dirs[-1]) / 'flet'
_zip_dir = Path(SPECPATH) / 'build'
_zip_dir.mkdir(parents=True, exist_ok=True)
_client_zip = _zip_dir / 'flet-windows.zip'
with zipfile.ZipFile(_client_zip, 'w', zipfile.ZIP_DEFLATED) as _zf:
    for _p in sorted(_client_flet.rglob('*')):
        _zf.write(_p, _p.relative_to(_client_flet.parent))

a = Analysis(
    ['mcbe_localization_hub.py'],
    pathex=[],
    binaries=rapidocr_binaries + onnx_binaries,
    datas=[('assets', 'assets'), (str(_client_zip), 'flet_desktop/app')] + rapidocr_datas + onnx_datas,
    hiddenimports=['openai', 'httpx', 'numpy', 'ssl'] + rapidocr_hiddenimports + onnx_hiddenimports,
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
