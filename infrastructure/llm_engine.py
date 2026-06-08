import os
import json
import httpx
from typing import Dict, Any, List
from utils.logger import get_logger
from dotenv import load_dotenv

load_dotenv()
logger = get_logger("LLMEngine")

class LLMEngine:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.resume_text = self._load_resume()
        
    def _load_resume(self) -> str:
        # Load from job_desc.txt or a dedicated resume.txt file
        try:
            with open("job_desc.txt", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("No job_desc.txt or resume.txt found to base answers on.")
            return "I am a skilled professional applying for this role."

    async def generate_answer(self, question: str, options: List[str] = None) -> str:
        if not self.api_key:
            logger.error("No OPENAI_API_KEY found. Cannot auto-answer.")
            return options[0] if options else "Yes"

        system_prompt = (
            "You are an autonomous AI agent applying for jobs on behalf of the user. "
            "You must answer application questions based strictly on the provided resume context. "
            "If the answer is not explicit in the resume, make a reasonable, positive, professional guess "
            "that maximizes the chances of getting the job. "
            "Keep the answer extremely concise (often 1 word to 1 sentence)."
        )
        if options:
            system_prompt += f" You MUST pick ONE exact match from this list of options: {json.dumps(options)}. Output NOTHING but the exact option."

        user_prompt = f"Resume Context:\n{self.resume_text}\n\nQuestion:\n{question}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 50
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=15.0)
                response.raise_for_status()
                data = response.json()
                answer = data["choices"][0]["message"]["content"].strip()
                return answer
        except Exception as e:
            logger.error(f"LLM API Error: {e}")
            return options[0] if options else "Yes"
