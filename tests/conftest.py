import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "environs" not in sys.modules:
    environs_module = types.ModuleType("environs")

    class _Env:
        def read_env(self) -> None:
            return None

        def str(self, _key: str, default: str | None = None) -> str:
            if default is None:
                return "test"
            return default

        def int(self, _key: str, default: int | None = None) -> int:
            if default is None:
                return 0
            return default

        def bool(self, _key: str, default: bool | None = None) -> bool:
            if default is None:
                return False
            return default

    environs_module.Env = _Env
    sys.modules["environs"] = environs_module

if "aiogram_newsletter" not in sys.modules:
    package = types.ModuleType("aiogram_newsletter")
    sys.modules["aiogram_newsletter"] = package

    handlers = types.ModuleType("aiogram_newsletter.handlers")

    class _Handlers:
        def register(self, _dispatcher: object) -> None:
            return None

    handlers.AiogramNewsletterHandlers = _Handlers
    sys.modules["aiogram_newsletter.handlers"] = handlers

    middleware = types.ModuleType("aiogram_newsletter.middleware")

    class _Middleware:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        async def __call__(self, handler, event, data):
            return await handler(event, data)

    middleware.AiogramNewsletterMiddleware = _Middleware
    sys.modules["aiogram_newsletter.middleware"] = middleware

    manager = types.ModuleType("aiogram_newsletter.manager")

    class _Manager:
        async def newsletter_menu(self, *_args: object, **_kwargs: object) -> None:
            return None

    manager.ANManager = _Manager
    sys.modules["aiogram_newsletter.manager"] = manager

if "redis" not in sys.modules:
    redis_pkg = types.ModuleType("redis")
    sys.modules["redis"] = redis_pkg

    redis_asyncio = types.ModuleType("redis.asyncio")

    class _Redis:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        @classmethod
        def from_url(cls, *_args: object, **_kwargs: object) -> "_Redis":
            return cls()

        def client(self) -> None:
            raise RuntimeError("Redis stub should not be used directly in tests.")

    redis_asyncio.Redis = _Redis
    sys.modules["redis.asyncio"] = redis_asyncio

if "apscheduler" not in sys.modules:
    apscheduler = types.ModuleType("apscheduler")
    sys.modules["apscheduler"] = apscheduler

    schedulers = types.ModuleType("apscheduler.schedulers")
    sys.modules["apscheduler.schedulers"] = schedulers

    async_mod = types.ModuleType("apscheduler.schedulers.asyncio")

    class _AsyncIOScheduler:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.jobs: list[tuple[str, tuple]] = []

        def start(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    async_mod.AsyncIOScheduler = _AsyncIOScheduler
    sys.modules["apscheduler.schedulers.asyncio"] = async_mod

    jobstores = types.ModuleType("apscheduler.jobstores")
    sys.modules["apscheduler.jobstores"] = jobstores

    jobstores_base = types.ModuleType("apscheduler.jobstores.base")

    class JobLookupError(Exception):
        pass

    jobstores_base.JobLookupError = JobLookupError
    sys.modules["apscheduler.jobstores.base"] = jobstores_base
