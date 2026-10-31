
import os

from dotenv import load_dotenv

load_dotenv()

from src import create_app

app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("EDUPULSE_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("EDUPULSE_DEBUG", "").lower()
        in {"1", "true", "yes"},
    )
