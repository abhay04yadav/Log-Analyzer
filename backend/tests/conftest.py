import os
import tempfile
from pathlib import Path

# isolated SQLite database, no Redis, no AI key, no background worker
_tmp = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.as_posix()}"
os.environ["REDIS_URL"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["RUN_WORKER"] = "false"
