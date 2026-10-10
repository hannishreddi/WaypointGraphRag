"""Eval runner. PLAN 1.4. Only `make eval-test` may pass --split test."""
import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.parse_args()
    raise SystemExit("make eval-*: not implemented yet (PLAN 1.4)")


if __name__ == "__main__":
    main()
