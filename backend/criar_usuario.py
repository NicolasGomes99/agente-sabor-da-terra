
import asyncio
import getpass

from api.database import get_session_maker
from api.repositories.user import UserRepository
from api.services.auth import AuthService


async def main():
    print("\n=== Cadastro de usuário ===\n")

    email = input("E-mail: ").strip().casefold()
    password = getpass.getpass("Senha: ")
    confirmation = getpass.getpass("Confirme a senha: ")

    if not email or "@" not in email:
        print("Erro: informe um e-mail válido.")
        return

    if len(password) < 8:
        print("Erro: a senha deve ter pelo menos 8 caracteres.")
        return

    if password != confirmation:
        print("Erro: as senhas não coincidem.")
        return

    session_maker = get_session_maker()

    async with session_maker() as session:
        try:
            repository = UserRepository(session)

            existing_user = await repository.get_by_email(email)
            if existing_user is not None:
                print("Erro: já existe um usuário com esse e-mail.")
                return

            hashed_password = AuthService.hash_password(password)

            user = await repository.create(
                email=email,
                password_hash=hashed_password,
            )

            await session.commit()

            print("\nUsuário cadastrado com sucesso!")
            print(f"E-mail: {user.email}")
            print(f"ID: {user.id}")

        except Exception:
            await session.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(main())
