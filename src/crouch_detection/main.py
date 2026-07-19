"""Application entry point. M1: runs the skeleton viewer."""

from crouch_detection import viewer


def main() -> int:
    return viewer.main()


if __name__ == "__main__":
    raise SystemExit(main())
