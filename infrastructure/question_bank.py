import json
import shutil
from pathlib import Path
from typing import Optional, Dict
from thefuzz import fuzz, process
from core.exceptions import QuestionBankMissError
from utils.logger import get_logger
from utils.config import settings

logger = get_logger("QuestionBank")

class QuestionBank:
    def __init__(self, custom_path: str = None):
        if custom_path:
            self.file_path = Path(custom_path)
            # If test bank doesn't exist, clone from the main bank
            main_bank = Path(settings.QUESTION_BANK_FILE)
            if not self.file_path.exists() and main_bank.exists():
                shutil.copy2(main_bank, self.file_path)
                logger.info(f"Cloned main question bank into {custom_path}")
        else:
            self.file_path = Path(settings.QUESTION_BANK_FILE)
            
        self.db: Dict[str, str] = self._load()
        
    def _load(self) -> Dict[str, str]:
        if not self.file_path.exists():
            # Initialize empty question bank
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump({}, f)
            return {}
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load question bank: {e}")
            return {}
            
    def _save(self):
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self.db, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save question bank: {e}")

    def get_answer(self, question_text: str) -> Optional[str]:
        """Get answer using fuzzy matching for high resilience"""
        if not self.db:
            raise QuestionBankMissError(question_text)
            
        questions = list(self.db.keys())
        
        def _process_ans(ans: str) -> str:
            if ans.startswith("__BRUTEFORCE__::"):
                return ans.split("::", 1)[1]
            return ans
        
        if question_text.startswith("ID_Q_"):
            if question_text in self.db:
                return _process_ans(self.db[question_text])
            else:
                # Still try fuzzy match, but only if the match is EXACTLY starting with ID_Q_ and score is very high?
                # Actually, no, if it's an ID, it should be an exact match to avoid false positives!
                raise QuestionBankMissError(question_text)

        # Extract best match
        best_match = process.extractOne(question_text, questions, scorer=fuzz.token_sort_ratio)
        if best_match:
            match_str, score = best_match
            # Don't match normal text to ID_Q_ keys if the text itself isn't an ID
            if score >= settings.FUZZY_MATCH_THRESHOLD and not match_str.startswith("ID_Q_"):
                logger.info(f"Fuzzy matched question (Score {score}): '{question_text}' -> '{match_str}'")
                return _process_ans(self.db[match_str])
                
        raise QuestionBankMissError(question_text)
        
    def add_answer(self, question_text: str, answer: str, is_bruteforce: bool = False):
        """Add a new answer to the bank"""
        if is_bruteforce:
            self.db[question_text] = f"__BRUTEFORCE__::{answer}"
            logger.warning(f"Added BRUTEFORCE answer for: '{question_text}'")
        else:
            self.db[question_text] = answer
            logger.success(f"Added new answer for: '{question_text}'")
        self._save()
