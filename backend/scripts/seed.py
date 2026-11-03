"""Development seed data. Run with `python manage.py seed`.

Use services from the container (not raw SQL) so seeded data follows the same rules as the API.
"""
from src.config.container import Container


async def run(container: Container) -> None:
    # Example:
    # await container.order_service().create(name="First order")
    print("Nothing to seed yet. Edit scripts/seed.py.")
