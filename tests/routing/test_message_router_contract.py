from pathlib import Path

import yaml


def test_message_routing_policy_has_safe_default_and_one_hop_limit() -> None:
    root = Path(__file__).parents[2]
    policy = yaml.safe_load((root / "config/message-routing.yaml").read_text())

    assert policy["schema_version"] == "message-routing-1.0.0"
    assert policy["policy"]["unknown_or_ambiguous"] == "default"
    assert policy["policy"]["max_hops"] == 1
    assert policy["policy"]["explicit_profile_route_wins"] is True
