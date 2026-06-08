class BotBlockedError(Exception):
    """Raised when the bot encounters Cloudflare, reCAPTCHA, or IP ban"""
    pass

class QuestionBankMissError(Exception):
    """Raised when an unknown question cannot be matched in the question bank"""
    def __init__(self, question_text: str):
        self.question_text = question_text
        super().__init__(f"No answer found for question: {question_text}")

class FormSolvingError(Exception):
    """Raised when a form element cannot be found or interacted with"""
    pass

class AuthError(Exception):
    """Raised when session cookies are invalid or expired"""
    pass
