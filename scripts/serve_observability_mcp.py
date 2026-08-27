"""Run the Hermes observability MCP bridge over stdio."""

from hermes_harness.mcp_server import create_server
from hermes_harness.runtime_mcp import build_bridge


def main() -> None:
    create_server(build_bridge()).run("stdio")


if __name__ == "__main__":
    main()
