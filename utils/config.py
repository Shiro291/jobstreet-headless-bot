import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

class Config:
    COOKIES_FILE = BASE_DIR / "cookies.json"
    QUESTION_BANK_FILE = BASE_DIR / "question_bank.json"
    
    # Matching confidence threshold for question fuzzy matching
    FUZZY_MATCH_THRESHOLD = int(os.getenv("FUZZY_MATCH_THRESHOLD", "80"))
    
    # Delay between job applications to avoid rate limits
    APPLY_DELAY_SECONDS = int(os.getenv("APPLY_DELAY_SECONDS", "5"))
    
    # Timeout settings
    PAGE_TIMEOUT = int(os.getenv("PAGE_TIMEOUT", "30000"))
    HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
    
settings = Config()
