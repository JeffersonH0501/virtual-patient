import os
import sys
import click
from alembic.config import Config
from alembic import command

@click.group()
def cli():
    """Database management commands."""
    pass

@cli.command()
def init():
    """Initialize the database."""
    from scripts.setup_db import create_database, create_tables
    create_database()
    create_tables()
    click.echo("Database initialized successfully!")

@cli.command()
@click.argument('message')
def migrate(message):
    """Create a new migration."""
    alembic_cfg = Config("alembic.ini")
    command.revision(alembic_cfg, message=message, autogenerate=True)
    click.echo(f"Migration created: {message}")

@cli.command()
def upgrade():
    """Apply all pending migrations."""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    click.echo("Migrations applied successfully!")

@cli.command()
def downgrade():
    """Rollback the last migration."""
    alembic_cfg = Config("alembic.ini")
    command.downgrade(alembic_cfg, "-1")
    click.echo("Last migration rolled back successfully!")

if __name__ == '__main__':
    cli() 