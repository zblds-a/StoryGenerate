"""Alembic 环境配置。

从 PersistenceSettings 读取 DATABASE_URL。
生产 Schema 修改必须通过 alembic upgrade head。
"""
from alembic import context
from sqlalchemy import engine_from_config, pool

from drama_engine.persistence.models import Base
from drama_engine.persistence.settings import PersistenceSettings

config = context.config
settings = PersistenceSettings.from_env()

if settings.backend == "postgres" and settings.database_url:
    config.set_main_option("sqlalchemy.url", settings.database_url)
elif settings.backend == "memory":
    # 内存模式不使用 Alembic
    pass

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线迁移（生成 SQL 脚本）。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线迁移（直接执行）。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if settings.backend == "postgres" and settings.database_url:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()