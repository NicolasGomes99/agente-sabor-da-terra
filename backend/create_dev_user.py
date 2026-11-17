import asyncio
from getpass import getpass

from api.database import get_engine, get_session_maker
from api.repositories.user import UserRepository
from api.services.auth import AuthService


async def main():
    email = input("E-mail para cadastro: ").strip().casefold()

    password = getpass("Defina sua senha: ")
    confirmation = getpass("Confirme sua senha: ")

    if not email or "@" not in email:
        print("E-mail inválido.")
        return

    if len(password) < 12:
        print("Use uma senha com pelo menos 12 caracteres.")
        return

    if password != confirmation:
        print("As senhas não coincidem.")
        return

    session_maker = get_session_maker()

    try:
        async with session_maker() as session:
            repository = UserRepository(session)

            existing_user = await repository.get_by_email(email)

            if existing_user:
                print("Já existe uma conta cadastrada com esse e-mail.")
                return

            password_hash = AuthService.hash_password(password)

            await repository.create(email, password_hash)
            await session.commit()

            print(f"Usuário {email} cadastrado com sucesso!")

    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())
