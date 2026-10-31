"""Production WSGI entry point for Waitress and compatible servers."""

import os

from dotenv import load_dotenv
from waitress import serve

load_dotenv()

from src import create_app


application = create_app()


if __name__ == "__main__":
    serve(
        application,
        host=os.environ.get("EDUPULSE_HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8080")),
    )
