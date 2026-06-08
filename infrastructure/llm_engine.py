import os
import json
import litellm
import asyncio
from typing import Dict, Any, List
from utils.logger import get_logger
from dotenv import load_dotenv

load_dotenv()
logger = get_logger("LLMEngine")

class LLMEngine:
    def __init__(self):
        # Allow user to specify ANY model, defaults to gpt-4o if not specified
        self.model = os.getenv("LLM_MODEL", "gpt-4o")
        self.api_key = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
        self.api_base = os.getenv("LLM_API_BASE", None)
        self.resume_text = self._load_resume()
        
    def _load_resume(self) -> str:
        try:
            with open("job_desc.txt", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("No job_desc.txt or resume.txt found to base answers on.")
            return "I am a skilled professional applying for this role."

    async def generate_answer(self, question: str, options: List[str] = None) -> str:
        # Local models via Ollama don't require an API key
        if not self.api_key and not self.api_base and not self.model.startswith("ollama/"):
            logger.error("No LLM_API_KEY or LLM_API_BASE found. Cannot auto-answer.")
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

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            # Using litellm.acompletion for async multi-provider support
            response = await litellm.acompletion(
                model=self.model,
                messages=messages,
                api_key=self.api_key if self.api_key else None,
                api_base=self.api_base,
                temperature=0.2,
                max_tokens=50
            )
            answer = response.choices[0].message.content.strip()
            return answer
        except Exception as e:
            logger.error(f"LLM API Error using model {self.model}: {e}")
            return options[0] if options else "Yes"
