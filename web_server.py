#!/usr/bin/env python3
"""Launch the Calendar Analytics web dashboard.

Run this to start a local web server with the analytics GUI.
All data is processed in-memory -- nothing is stored to disk.

Usage:
    python web_server.py                    # Default: port 5000
    python web_server.py --port 8080        # Custom port
    python web_server.py --config my.yaml   # Custom config
"""

import click

from cal_analyzer.web.app import create_app


@click.command()
@click.option("--port", "-p", default=5000, help="Port to run on.")
@click.option("--host", "-h", default="127.0.0.1", help="Host to bind to.")
@click.option("--config", "-c", default="config.yaml", help="Path to config YAML file.")
@click.option("--debug", is_flag=True, help="Enable debug mode.")
def main(port, host, config, debug):
    """Start the Calendar Analytics web dashboard."""
    app = create_app(config_path=config)
    click.echo(f"\n  Calendar Analytics Dashboard")
    click.echo(f"  http://{host}:{port}\n")
    click.echo(f"  Upload an .ics file or paste an iCal URL to get started.")
    click.echo(f"  Press Ctrl+C to stop.\n")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
