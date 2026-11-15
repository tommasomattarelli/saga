from uuid import uuid4

from app.ai.session_affinity import campaign_session, campaign_session_affinity


def test_campaign_session_affinity_is_scoped_and_restored() -> None:
    campaign_id = uuid4()

    assert campaign_session_affinity() is None
    with campaign_session(campaign_id):
        assert campaign_session_affinity() == str(campaign_id)
    assert campaign_session_affinity() is None
