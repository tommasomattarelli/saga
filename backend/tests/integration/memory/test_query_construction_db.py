from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.query_construction import build_lexical_query


async def test_lexical_query_or_prefixes_gazetteer_names(db_session: AsyncSession) -> None:
    expression = await build_lexical_query(
        db_session, "Lyra promised the silver key", ["Lyra", "Silver"]
    )

    assert set(expression.split(" | ")) == {"lyra:*", "silver:*", "promised", "the", "key"}
