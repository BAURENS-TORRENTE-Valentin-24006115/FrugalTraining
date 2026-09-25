"""Point d'entrée du programme."""

import asyncio

from workflow import main_async


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n[+] Interruption du programme.")


if __name__ == "__main__":
    main()
