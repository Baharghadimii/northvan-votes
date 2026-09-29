"""North Van Votes pipeline.

Loads .env on import so every stage (and the fetcher's contact-email User-Agent)
sees the same configuration whether it is run as a module or imported.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
