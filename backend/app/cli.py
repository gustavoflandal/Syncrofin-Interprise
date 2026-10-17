"""CLI commands for managing the application."""
import asyncio
import getpass
import sys
import uuid

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.user import User


async def generate_recurring() -> None:
    """Generate pending recurring transactions for all users."""
    from app.models.user import User as UserModel
    from app.services import recurring_transaction_service

    async with async_session_maker() as session:
        result = await session.execute(select(UserModel))
        users = result.scalars().all()
        total = 0
        for user in users:
            count = await recurring_transaction_service.generate_pending(session, user.id)
            if count > 0:
                print(f"Generated {count} transactions for {user.email}")
                total += count
        print(f"Total generated: {total}")


async def create_user(email: str, password: str) -> None:
    """Create a new user with the given email and password."""
    from pwdlib import PasswordHash

    from app.core import password_policy

    reason = password_policy.first_problem(password, email=email)
    if reason is not None:
        print(f"Error: {password_policy.describe(reason)}")
        sys.exit(1)

    hasher = PasswordHash.recommended()

    async with async_session_maker() as session:
        # Check if user already exists
        result = await session.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing:
            print(f"Error: User with email '{email}' already exists.")
            sys.exit(1)

        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=hasher.hash(password),
            is_active=True,
            is_superuser=False,
            is_verified=True,
            preferences={
                "language": "pt-BR",
                "date_format": "DD/MM/YYYY",
                "timezone": "America/Sao_Paulo",
                "currency_display": "USD",
            },
        )
        session.add(user)
        await session.commit()
        print(f"User created successfully: {email}")


async def unlock_user(email: str) -> None:
    """Lift the pause on an account locked by wrong passwords (for when no administrator can sign in)."""
    from app.services import login_guard

    async with async_session_maker() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            print(f"Error: no user with email '{email}'.")
            sys.exit(1)
        lifted = await login_guard.unlock(session, user.id, reason="cli")
        await session.commit()
        print("Account unlocked." if lifted else "The account was not locked.")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m app.cli create-user <email> [password]   (asks for the password when omitted)")
        print("  python -m app.cli unlock-user <email>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "create-user":
        if len(sys.argv) not in (3, 4):
            print("Usage: python -m app.cli create-user <email> [password]")
            sys.exit(1)
        email = sys.argv[2]
        # A password on the command line stays in the shell history and shows in `ps`: ask for it instead.
        password = sys.argv[3] if len(sys.argv) == 4 else getpass.getpass("Password: ")
        asyncio.run(create_user(email, password))
    elif command == "unlock-user":
        if len(sys.argv) != 3:
            print("Usage: python -m app.cli unlock-user <email>")
            sys.exit(1)
        asyncio.run(unlock_user(sys.argv[2]))
    elif command == "generate-recurring":
        asyncio.run(generate_recurring())
    else:
        print(f"Unknown command: {command}")
        print("Available commands: create-user, unlock-user, generate-recurring")
        sys.exit(1)


if __name__ == "__main__":
    main()
