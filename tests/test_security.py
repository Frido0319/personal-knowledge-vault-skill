from pathlib import Path

import pytest

from personal_vault.security import (
    SecurityBoundaryError,
    find_secret_matches,
    is_forbidden_relative_path,
    redact_text,
    validate_authorized_root,
)


@pytest.mark.parametrize(
    "relative",
    [
        ".env",
        "nested/.env.production",
        ".ssh/id_ed25519",
        ".gnupg/private-keys-v1.d/key",
        "wallet/seed.txt",
        "Cookies",
        "Default/Login Data",
    ],
)
def test_sensitive_paths_are_forbidden(relative: str) -> None:
    assert is_forbidden_relative_path(relative)


def test_secret_detection_and_redaction_do_not_return_values() -> None:
    github_prefix = "gh" + "p_"
    openai_prefix = "sk" + "-proj-"
    text = (
        "mail alice@example.com phone +86 13800138000 "
        f"token {github_prefix}abcdefghijklmnopqrstuvwxyz1234567890AB "
        f"api_key={openai_prefix}abcdefghijklmnopqrstuvwxyz"
    )

    matches = find_secret_matches(text)
    redacted = redact_text(text)

    assert {match.kind for match in matches} >= {"email", "phone", "github_token", "openai_key"}
    assert "alice@example.com" not in redacted
    assert "13800138000" not in redacted
    assert github_prefix not in redacted
    assert openai_prefix not in redacted
    assert redacted.count("[REDACTED:") >= 4


@pytest.mark.parametrize("root_name", ["filesystem", "home"])
def test_authorized_source_rejects_dangerous_broad_roots(tmp_path: Path, root_name: str) -> None:
    home = tmp_path / "home"
    home.mkdir()
    root = Path("/") if root_name == "filesystem" else home

    with pytest.raises(SecurityBoundaryError, match="ROOT_TOO_BROAD"):
        validate_authorized_root(root, home=home)


def test_authorized_source_rejects_symlink_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)

    with pytest.raises(SecurityBoundaryError, match="SYMLINK_ROOT"):
        validate_authorized_root(link, home=tmp_path / "home")
