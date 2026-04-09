"""game_paths.ensure_rpgmaker_mz_project_shell 테스트.

tmp_path에 base_game과 game_root를 만들어 테스트.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture()
def base_and_game(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """base_game과 game_root를 tmp_path에 구성."""
    from app.backend.core.config import settings

    base = tmp_path / "base_game"
    base.mkdir()
    (base / "game.rmmzproject").write_text("{}", encoding="utf-8")
    (base / "package.json").write_text("{}", encoding="utf-8")
    (base / "index.html").write_text("<html/>", encoding="utf-8")
    css = base / "css"
    css.mkdir()
    (css / "main.css").write_text("body{}", encoding="utf-8")
    js = base / "js"
    js.mkdir()
    (js / "main.js").write_text("//js", encoding="utf-8")

    game_root = tmp_path / "game_001"
    game_root.mkdir()
    (game_root / "data").mkdir()

    monkeypatch.setattr(settings, "BASE_GAME_PATH", str(base))

    return base, game_root


class TestEnsureRpgmakerMzProjectShell:
    def test_copies_root_files(self, base_and_game) -> None:
        from app.backend.core.game_paths import ensure_rpgmaker_mz_project_shell

        _, game_root = base_and_game
        ensure_rpgmaker_mz_project_shell(game_root)

        assert (game_root / "game.rmmzproject").exists()
        assert (game_root / "package.json").exists()
        assert (game_root / "index.html").exists()

    def test_copies_css_dir(self, base_and_game) -> None:
        from app.backend.core.game_paths import ensure_rpgmaker_mz_project_shell

        _, game_root = base_and_game
        ensure_rpgmaker_mz_project_shell(game_root)

        assert (game_root / "css" / "main.css").exists()

    def test_symlinks_js_posix(self, base_and_game) -> None:
        from app.backend.core.game_paths import ensure_rpgmaker_mz_project_shell

        _, game_root = base_and_game
        ensure_rpgmaker_mz_project_shell(game_root)

        js_dst = game_root / "js"
        if os.name == "posix":
            assert js_dst.is_symlink()
            assert (js_dst / "main.js").exists()
        else:
            # Windows: 심볼릭 링크 없이 생략
            pass

    def test_skips_existing(self, base_and_game) -> None:
        from app.backend.core.game_paths import ensure_rpgmaker_mz_project_shell

        _, game_root = base_and_game
        # 미리 파일 생성
        (game_root / "game.rmmzproject").write_text("existing", encoding="utf-8")

        ensure_rpgmaker_mz_project_shell(game_root)

        # 기존 파일이 덮어쓰이지 않음
        assert (game_root / "game.rmmzproject").read_text() == "existing"

    def test_missing_base_is_noop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.backend.core.config import settings
        from app.backend.core.game_paths import ensure_rpgmaker_mz_project_shell

        monkeypatch.setattr(settings, "BASE_GAME_PATH", str(tmp_path / "nonexistent"))
        game_root = tmp_path / "game"
        game_root.mkdir()

        # 에러 없이 종료
        ensure_rpgmaker_mz_project_shell(game_root)

    def test_missing_game_root_is_noop(self, base_and_game) -> None:
        from app.backend.core.game_paths import ensure_rpgmaker_mz_project_shell

        _, _ = base_and_game
        nonexistent = Path("/tmp/nonexistent_game_root_xyz")
        # 에러 없이 종료
        ensure_rpgmaker_mz_project_shell(nonexistent)
