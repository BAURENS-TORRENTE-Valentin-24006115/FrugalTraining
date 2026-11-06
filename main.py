"""Point d'entrée du programme."""

import asyncio
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="FrugalTraining")
    parser.add_argument("--cli", action="store_true", help="lancer l'ancien mode console")
    parser.add_argument("--debug", action="store_true", help="activer les outils de développement de l'interface")
    args = parser.parse_args()
    try:
        if args.cli:
            from workflow import main_async
            asyncio.run(main_async())
        else:
            from interface import launch_windows
            launch_windows(debug=args.debug)
    except KeyboardInterrupt:
        print("\n[+] Interruption du programme.")


if __name__ == "__main__":
    main()
