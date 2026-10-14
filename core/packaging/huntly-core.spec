# PyInstaller spec for the Huntly core sidecar. Build with scripts/build-sidecar.sh.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

datas = [
    ("../huntly/assets/fonts", "huntly/assets/fonts"),
    ("../huntly/migrations", "huntly/migrations"),
]
datas += collect_data_files("googleapiclient")  # static Gmail discovery document
datas += collect_data_files("tzdata")

hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("keyring.backends")
    + collect_submodules("huntly")
    + ["alembic.runtime.migration", "alembic.ddl.sqlite", "sqlalchemy.dialects.sqlite"]
)

a = Analysis(
    ["launcher.py"],
    pathex=[".."],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="huntly-core",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    runtime_tmpdir=None,
)
