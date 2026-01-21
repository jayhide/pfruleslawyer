#!/usr/bin/env python3
"""CLI for running the Pathfinder Rules Lawyer API server."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Run the Pathfinder Rules Lawyer API server"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)"
    )

    args = parser.parse_args()

    try:
        import uvicorn
        uvicorn.run(
            "pfruleslawyer.web.app:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            workers=args.workers if not args.reload else 1,
        )
    except KeyboardInterrupt:
        print("\nServer stopped", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
