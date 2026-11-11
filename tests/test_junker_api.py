from collections.abc import AsyncGenerator
from typing import Any

import pytest
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer

import junker_api
from junker_api import (
    _EVENTS_RE,
    AreaRequired,
    JunkerClient,
    JunkerConnectionError,
    JunkerError,
    slugify_municipality,
)

AREA_NAME_KEY = "NOME"  # codespell:ignore nome
EVENTS = 'var events = [{"date":"2026-11-12","vbin_desc":"Paper"}];'
URL = "/test-municipality/calendario"
AREA_URL = "/test-municipality/1/calendario"


class Responses:
    """Responses served by the fake Junker server, keyed by path."""

    def __init__(self) -> None:
        """Initialize the responses."""
        self.routes: dict[str, tuple[int, str]] = {}

    def get(self, path: str, body: str = "", status: int = 200) -> None:
        """Register a response."""
        self.routes[path] = (status, body)

    async def handler(self, request: web.Request) -> web.Response:
        """Serve a registered response."""
        status, body = self.routes.get(request.path, (404, ""))
        return web.Response(status=status, text=body)


@pytest.fixture
async def mock(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[Responses]:
    """Run a fake Junker server and point the library at it."""
    responses = Responses()
    app = web.Application()
    app.router.add_get("/{tail:.*}", responses.handler)
    async with TestServer(app) as server:
        monkeypatch.setattr(
            junker_api, "_BASE_URL", str(server.make_url("")).rstrip("/")
        )
        yield responses


@pytest.fixture
async def client(mock: Responses) -> AsyncGenerator[JunkerClient]:
    """Return a client with a real session."""
    async with ClientSession() as session:
        yield JunkerClient(session, "Test municipality")


def test_slugify_municipality() -> None:
    """Test municipality names are converted to Junker URL slugs."""
    assert slugify_municipality("Lodè d'Italia") == "lode-d-italia"


def test_extract_events_from_calendar_page() -> None:
    """Test that events are extracted from the calendar JavaScript."""
    match = _EVENTS_RE.search('var events = [{"date":"2026-11-12"}];')
    assert match is not None
    assert match.group(1) == '[{"date":"2026-11-12"}]'


def test_parse_collections() -> None:
    """Test embedded event data is parsed into collections."""
    collections = JunkerClient._parse_collections(
        '[{"date":"2026-11-12","vbin_desc":"Paper"}]'
    )
    assert [(str(c.date), c.waste_type) for c in collections] == [
        ("2026-11-12", "Paper")
    ]


@pytest.mark.parametrize(
    "events", ["[]", '[{"date":"x","vbin_desc":"Paper"}]', "not json"]
)
def test_parse_invalid_collections(events: str) -> None:
    """Test invalid event data raises a Junker error."""
    with pytest.raises(JunkerError):
        JunkerClient._parse_collections(events)


async def test_get_collections(client: JunkerClient, mock: Responses) -> None:
    """Test fetching the collections of a municipality."""
    mock.get(URL, body=EVENTS)
    collections = await client.async_get_collections()
    assert [(str(c.date), c.waste_type) for c in collections] == [
        ("2026-11-12", "Paper")
    ]


async def test_get_collections_with_area(mock: Responses) -> None:
    """Test fetching the collections of an area."""
    mock.get(AREA_URL, body=EVENTS)
    async with ClientSession() as session:
        client = JunkerClient(session, "Test municipality", "1")
        assert len(await client.async_get_collections()) == 1


async def test_area_required(client: JunkerClient, mock: Responses) -> None:
    """Test a municipality with areas requires a selection."""
    mock.get(URL, body=f'var zone = [{{"ID":1,"{AREA_NAME_KEY}":"Central"}}];')
    with pytest.raises(AreaRequired) as err:
        await client.async_get_collections()
    assert [(a.id, a.name) for a in err.value.areas] == [(1, "Central")]


async def test_empty_areas_use_events(client: JunkerClient, mock: Responses) -> None:
    """Test an empty area list falls back to the events."""
    mock.get(URL, body=f"var zone = [];\n{EVENTS}")
    assert len(await client.async_get_collections()) == 1


async def test_invalid_areas(client: JunkerClient, mock: Responses) -> None:
    """Test invalid area data raises a Junker error."""
    mock.get(URL, body='var zone = [{"ID":1}];')
    with pytest.raises(JunkerError):
        await client.async_get_collections()


@pytest.mark.parametrize(("status", "body"), [(404, ""), (200, "no calendar here")])
async def test_request_errors(
    client: JunkerClient, mock: Responses, status: int, body: str
) -> None:
    """Test missing calendars raise a Junker error, not a connection error."""
    mock.get(URL, status=status, body=body)
    with pytest.raises(JunkerError) as err:
        await client.async_get_collections()
    assert not isinstance(err.value, JunkerConnectionError)


async def test_server_error(client: JunkerClient, mock: Responses) -> None:
    """Test server errors raise a connection error."""
    mock.get(URL, status=500)
    with pytest.raises(JunkerConnectionError):
        await client.async_get_collections()


async def test_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test timeouts raise a connection error."""

    class TimeoutSession:
        def get(self, *args: Any, **kwargs: Any) -> Any:
            raise TimeoutError

    client = JunkerClient(TimeoutSession(), "Test municipality")  # type: ignore[arg-type]
    with pytest.raises(JunkerConnectionError):
        await client.async_get_collections()
