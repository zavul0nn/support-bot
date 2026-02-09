import asyncio
from types import SimpleNamespace

from app.bot.handlers.private.windows import Window
from app.bot.utils.texts import TextMessage


class DummySettings:
    def __init__(self, greetings: dict[str, str]):
        self._greetings = greetings

    async def get_greeting(self, language: str) -> str | None:
        return self._greetings.get(language)


class DummyState:
    def __init__(self) -> None:
        self.calls: list[str | None] = []

    async def set_state(self, value: str | None) -> None:
        self.calls.append(value)


class DummyText(TextMessage):
    def __init__(self, language_code: str, default_text: str) -> None:
        super().__init__(language_code)
        self._default_text = default_text

    @property
    def data(self) -> dict:
        return {
            self.language_code: {
                "main_menu": self._default_text,
            }
        }


class DummyManager:
    def __init__(self, language_code: str, settings: DummySettings | None, default_text: str) -> None:
        self.text_message = DummyText(language_code, default_text)
        self.user = SimpleNamespace(full_name="John Doe")
        self._middleware_data = {"settings": settings} if settings else {}
        self.state = DummyState()
        self.sent_messages: list[str] = []

    @property
    def middleware_data(self) -> dict:
        return self._middleware_data

    async def send_message(self, text: str, **_: str) -> None:
        self.sent_messages.append(text)


def test_main_menu_uses_custom_greeting() -> None:
    settings = DummySettings({"en": "Welcome {full_name}"})
    manager = DummyManager("en", settings, "Default {full_name}")

    asyncio.run(Window.main_menu(manager))

    assert manager.sent_messages == ["Welcome <b>John Doe</b>"]
    assert manager.state.calls[-1] is None


def test_main_menu_falls_back_to_default_text() -> None:
    manager = DummyManager("en", settings=None, default_text="Default {full_name}")

    asyncio.run(Window.main_menu(manager))

    assert manager.sent_messages == ["Default <b>John Doe</b>"]
    assert manager.state.calls[-1] is None
