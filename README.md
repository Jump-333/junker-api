# junker-api

Async Python client for the public waste collection calendars published by [Junker](https://www.junker.app/).

It fetches the calendar page of a municipality (and optionally one of its areas) and returns the scheduled collections.

## Installation

```bash
pip install junker-api
```

## Usage

```python
import asyncio

from aiohttp import ClientSession

from junker_api import AreaRequired, JunkerClient, JunkerConnectionError, JunkerError


async def main() -> None:
    async with ClientSession() as session:
        client = JunkerClient(session, "Milano")
        try:
            collections = await client.async_get_collections()
        except AreaRequired as err:
            # The municipality has several areas: pick one and retry.
            area = err.areas[0]
            client = JunkerClient(session, "Milano", str(area.id))
            collections = await client.async_get_collections()
        except JunkerConnectionError:
            print("Junker is not reachable")
            return
        except JunkerError:
            print("No calendar found for this municipality")
            return

        for collection in collections:
            print(collection.date, collection.waste_type)


asyncio.run(main())
```

## API

- `JunkerClient(session, municipality, area_id=None)`: client bound to a municipality and an optional area ID.
- `await client.async_get_collections()`: returns a list of `Collection(date, waste_type)` sorted by date.
- `slugify_municipality(name)`: converts a municipality name into the slug used in Junker URLs.

### Exceptions

- `JunkerError`: base error, also raised when the calendar does not exist or cannot be parsed.
- `JunkerConnectionError`: network failure, timeout or HTTP 5xx response.
- `AreaRequired`: the municipality requires an area; the available `Area(id, name)` items are in `err.areas`.

## Development

```bash
pip install -e ".[test]"
python -m pytest --cov=junker_api --cov-report=term-missing
```

## Disclaimer

This project is not affiliated with Junker. It relies on Junker's public web pages, which may change without notice.

## License

Apache-2.0
