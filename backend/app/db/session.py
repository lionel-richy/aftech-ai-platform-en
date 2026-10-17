"""SQLAlchemy async engine and sessions — LOCAL DEVELOPMENT ONLY.

Never imported by app/main.py as long as this layer isn't wired into the
deployed application (see docs/DATABASE.md). No DATABASE_URL = DB
features are simply unavailable, never a crash at startup.
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

# IMPORTANT: "aftech_app" (not "aftech", the tables' owner) — in
# PostgreSQL, a table's owner (and any BYPASSRLS role) simply ignores RLS
# policies. Only a connection using a restricted role like this one
# actually enforces per-organization isolation (see migration 0001, which
# creates this role).
DATABASE_URL_DEFAUT = "postgresql+asyncpg://aftech_app:aftech-app-dev-local@localhost:5432/aftech"


def url_base_de_donnees() -> str:
    return os.environ.get("DATABASE_URL", DATABASE_URL_DEFAUT)


DATABASE_URL_ADMIN_DEFAUT = "postgresql+asyncpg://aftech:aftech-dev-local@localhost:5432/aftech"


def url_base_de_donnees_admin() -> str:
    return os.environ.get("DATABASE_URL_ADMIN", DATABASE_URL_ADMIN_DEFAUT)


_engine: AsyncEngine | None = None
_fabrique_session: async_sessionmaker[AsyncSession] | None = None
_engine_admin: AsyncEngine | None = None
_fabrique_session_admin: async_sessionmaker[AsyncSession] | None = None


def obtenir_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(url_base_de_donnees(), pool_pre_ping=True)
    return _engine


def obtenir_fabrique_session() -> async_sessionmaker[AsyncSession]:
    global _fabrique_session
    if _fabrique_session is None:
        _fabrique_session = async_sessionmaker(obtenir_engine(), expire_on_commit=False)
    return _fabrique_session


def _obtenir_engine_admin() -> AsyncEngine:
    global _engine_admin
    if _engine_admin is None:
        _engine_admin = create_async_engine(url_base_de_donnees_admin(), pool_pre_ping=True)
    return _engine_admin


def _obtenir_fabrique_session_admin() -> async_sessionmaker[AsyncSession]:
    global _fabrique_session_admin
    if _fabrique_session_admin is None:
        _fabrique_session_admin = async_sessionmaker(_obtenir_engine_admin(), expire_on_commit=False)
    return _fabrique_session_admin


@asynccontextmanager
async def session_pour_organisation(organization_id: str) -> AsyncIterator[AsyncSession]:
    """Opens a session with the RLS context set for THIS organization
    (see migration 0001: the policies read
    current_setting('app.current_org_id')). set_config(..., true) = scope
    local to the transaction only, never leaked to another request that
    would reuse the same pooled connection."""
    fabrique = obtenir_fabrique_session()
    async with fabrique() as session:
        async with session.begin():
            await session.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": organization_id})
            yield session


@asynccontextmanager
async def session_administrateur() -> AsyncIterator[AsyncSession]:
    """Connection using the tables' OWNER role ("aftech"): deliberately
    bypasses RLS policies — reserved for administration scripts and tests
    that need to read/write ACROSS multiple organizations. NEVER used
    from a normal HTTP route (see obtenir_fabrique_session, which uses
    the restricted "aftech_app" role)."""
    fabrique = _obtenir_fabrique_session_admin()
    async with fabrique() as session:
        yield session


async def fermer_engine() -> None:
    global _engine, _fabrique_session, _engine_admin, _fabrique_session_admin
    if _engine is not None:
        await _engine.dispose()
    if _engine_admin is not None:
        await _engine_admin.dispose()
    _engine = None
    _fabrique_session = None
    _engine_admin = None
    _fabrique_session_admin = None
