# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files


a = Analysis(
    ['studio.py'],
    pathex=[],
    binaries=[],
    datas=collect_data_files('tkinterdnd2'),
    hiddenimports=['tkinterdnd2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Scan Names (torch + transformers, ~7 GB với CUDA) chỉ chạy từ source;
    # đóng gói vào exe sẽ vượt giới hạn 100 MB/file của GitHub.
    excludes=['torch', 'torchvision', 'torchaudio', 'transformers', 'tokenizers', 'safetensors',
              'huggingface_hub', 'triton', 'tensorflow', 'jax', 'scipy', 'sklearn', 'pandas',
              'matplotlib', 'IPython', 'notebook', 'onnxruntime',
              # name_scanner.py (jieba) không còn được builder/studio dùng; numpy chỉ do jieba kéo vào.
              'jieba', 'numpy'],
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
    name='StoryStudio',
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
)
