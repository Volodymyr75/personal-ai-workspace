from alembic import context

from paw.config import Settings
from paw.infrastructure.db.connection import make_engine
from paw.infrastructure.db.tables import metadata

# Do not put database credentials in alembic.ini or print the DSN.
if context.is_offline_mode():
    context.configure(dialect_name="postgresql", target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif context.config.attributes.get("connection") is not None:
    context.configure(connection=context.config.attributes["connection"], target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = make_engine(Settings())
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
