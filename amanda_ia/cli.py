"""CLI de Amanda-IA."""

from dotenv import load_dotenv

load_dotenv()

from amanda_ia.agent import run


def main():
    """Punto de entrada."""
    run()
