from fastapi import APIRouter

from app.deps import CurrentUser, SessionDep
from app.models import ROLE_TITLES, User
from app.schemas import LoginIn, LoginOut, UserOut
from app.services.auth import authenticate, create_token
from app.services.permissions import perms_for

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        role_title=ROLE_TITLES.get(user.role, user.role),  # type: ignore[call-overload]
        permissions=perms_for(user.role),
    )


@router.post("/login", response_model=LoginOut)
async def login(body: LoginIn, session: SessionDep) -> LoginOut:
    user = await authenticate(session, body.username, body.password)
    return LoginOut(token=create_token(user), user=user_out(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return user_out(user)
