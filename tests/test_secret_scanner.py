from scripts.check_secrets import PATTERNS


def test_openai_pattern_matches_example() -> None:
    assert PATTERNS["openai"].search("sk-proj-abcdefghijklmnopqrstuvwxyz0123456789")


def test_telegram_pattern_matches_example() -> None:
    assert PATTERNS["telegram_bot_token"].search("123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
