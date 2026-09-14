import uvicorn

from mapc.app import appsettings


def main() -> None:
    uvicorn.run(
        "mapc.app:app",
        host=appsettings.host,
        port=appsettings.port,
    )


if __name__ == "__main__":
    main()
