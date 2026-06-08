import sys
from loguru import logger

# Remove default handler
logger.remove()

# Add console handler with colors
logger.add(sys.stdout, colorize=True, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")

# Add file handler for persistent logs
logger.add("bot.log", rotation="10 MB", retention="10 days", level="DEBUG")

def get_logger(name: str):
    return logger.bind(name=name)
