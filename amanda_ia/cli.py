"""CLI de Amanda-IA."""

import argparse

from dotenv import load_dotenv

load_dotenv()

from amanda_ia.agent import run, process
from amanda_ia.agent import console


def main():
    """Punto de entrada."""
    parser = argparse.ArgumentParser(prog="aia")
    parser.add_argument("-m", "--message", help="Mensaje único: responde y termina sin abrir la CLI")
    args = parser.parse_args()

    if args.message is not None:
        response = process(args.message)
        console.print(response)
        return

    run()
