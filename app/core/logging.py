import logging
import sys

from loguru import logger

from app.core.config import settings


class InterceptHandler(logging.Handler):
    """把标准 logging（uvicorn / sqlalchemy 等第三方库用的）转发给 loguru，
    统一输出格式。类比 Node 里把其他库的 log 都汇入同一个 pino 实例。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame.f_back and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def  setup_logging() -> None:
    logger.remove()  # 移除 loguru 默认 handler，自己重新配置

    logger.add(
        sys.stdout,
        level="DEBUG" if settings.debug else "INFO",
        colorize=True,
        backtrace=True,
        diagnose=settings.debug,  # 生产环境关掉，避免报错时把变量值打出去
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
            "- <level>{message}</level>"
        ),
    )

    # 落盘：按天切割，保留 14 天，自动 zip 压缩，方便以后排查线上问题
    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        level="INFO",
        rotation="00:00",
        retention="14 days",
        compression="zip",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    # 接管 uvicorn / sqlalchemy 等标准库 logger（包括 db.py 里 echo=True 打的 SQL）
    logging.root.handlers = [InterceptHandler()]
    logging.root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(name).handlers = [InterceptHandler()]
        logging.getLogger(name).propagate = False