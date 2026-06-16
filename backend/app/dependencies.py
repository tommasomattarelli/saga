from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def seed_templates() -> None:
    from pathlib import Path

    import yaml
    from sqlalchemy import select

    from app.models.template import Template

    root_dir = Path(__file__).resolve().parent.parent.parent
    # In Docker, templates are mounted at /templates.
    # Locally, they live at <project_root>/templates.
    templates_dir = Path("/templates") if Path("/templates").exists() else root_dir / "templates"
    if not templates_dir.exists():
        return

    # Using a local session to ensure we don't interfere with the main engine transaction
    async with async_session() as db:
        for template_file in templates_dir.glob("**/template.yaml"):
            try:
                with open(template_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if not data.get("schema_version"):
                    from structlog import get_logger

                    get_logger().error(
                        "template_missing_schema_version",
                        file=str(template_file),
                    )
                    continue

                meta = data.get("meta", {})
                slug = meta.get("slug")
                if not slug:
                    continue

                # Remove meta from content to avoid redundancy
                content = {k: v for k, v in data.items() if k != "meta"}

                # Check for existence (Upsert)
                result = await db.execute(select(Template).where(Template.slug == slug))
                existing = result.scalar_one_or_none()

                if existing:
                    existing.name = meta.get("name", existing.name)
                    existing.description = meta.get("description", existing.description)
                    existing.author = meta.get("author", existing.author)
                    existing.version = meta.get("version", existing.version)
                    existing.difficulty = meta.get("difficulty", existing.difficulty)
                    existing.tags = meta.get("tags", existing.tags)
                    existing.content = content
                else:
                    new_template = Template(
                        slug=slug,
                        name=meta.get("name", "Unknown"),
                        description=meta.get("description", ""),
                        author=meta.get("author", "Unknown"),
                        version=meta.get("version", "1.0"),
                        difficulty=meta.get("difficulty", 5),
                        tags=meta.get("tags", []),
                        content=content,
                    )
                    db.add(new_template)

            except Exception as e:
                from structlog import get_logger

                get_logger().error("template_seed_failed", file=str(template_file), error=str(e))

        await db.commit()


async def init_db() -> None:
    from app.models.base import Base  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await seed_templates()


async def close_db() -> None:
    await engine.dispose()


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session


def get_db_context():
    return async_session()
