# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['builder_qt.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['moxhi_scanner', 'moxhi_numpy', 'sentencepiece'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # torch + transformers (~7 GB với CUDA) không đóng gói được (giới hạn 100 MB/file của GitHub).
    # Quét tên trong exe dùng Moxhi chạy bằng numpy + sentencepiece (moxhi_numpy.py), chỉ CPU;
    # BERT NER chỉ chạy từ source.
    excludes=['torch', 'torchvision', 'torchaudio', 'transformers', 'tokenizers', 'safetensors',
              'huggingface_hub', 'triton', 'tensorflow', 'jax', 'scipy', 'sklearn', 'pandas',
              'matplotlib', 'IPython', 'notebook', 'onnxruntime',
              # name_scanner.py (jieba) không còn được builder/studio dùng.
              'jieba',
              # Giao diện là Qt (PySide6): không cần Tk; bỏ các mô-đun Qt không dùng cho nhẹ.
              'tkinter', '_tkinter', 'tkinterdnd2',
              'PySide6.QtNetwork', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtOpenGL',
              'PySide6.QtOpenGLWidgets', 'PySide6.QtPdf', 'PySide6.QtSvg', 'PySide6.QtDBus',
              'PySide6.QtConcurrent', 'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtXml'],
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
    name='StoryTranslatorPro',
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
