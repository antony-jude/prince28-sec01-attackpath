"""Send 50 requests and report the SQLAlchemy pool status."""

import httpx


def main() -> None:
    base_url = "http://127.0.0.1:8000"
    counts: dict[int, int] = {}
    with httpx.Client(base_url=base_url, timeout=5.0) as client:
        for _ in range(50):
            response = client.get("/ready")
            counts[response.status_code] = counts.get(response.status_code, 0) + 1
    print(f"50 /ready requests completed: {counts}")


if __name__ == "__main__":
    main()
