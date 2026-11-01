"""Run the addition demo with python -m rust_add"""

from . import add


def main() -> None:
    print(f"add(2, 3) = {add(2, 3)}")


if __name__ == "__main__":
    main()
