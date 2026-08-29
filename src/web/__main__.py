"""``python -m src.web`` — run the dashboard server."""

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the red-team dashboard web server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default 0.0.0.0, LAN reachable)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default 8000)")
    args = parser.parse_args()
    uvicorn.run("src.web.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
