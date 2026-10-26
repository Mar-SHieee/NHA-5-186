import pandas as pd
import pytest

from shield_core.datasets.pipeline.project_normalization import (
    add_normalized_project_column,
    find_shared_commit_project_names,
    normalize_project_name,
    reload_learned_aliases,
)


@pytest.fixture(autouse=True)
def clear_learned_aliases(tmp_path):
    empty_file = tmp_path / "empty.json"
    empty_file.write_text('{"aliases": {}}', encoding="utf-8")
    reload_learned_aliases(empty_file)
    yield
    reload_learned_aliases(empty_file)


def test_project_names_are_lowercase():
    assert normalize_project_name("FFmpeg") == "ffmpeg"
    assert normalize_project_name("ANDROID") == "android"


def test_project_name_whitespace_and_slashes():
    assert normalize_project_name("  FFmpeg  ") == "ffmpeg"
    assert normalize_project_name(r"torvalds\linux") == "torvalds/linux"


def test_github_url_and_git_suffix_cleanup():
    assert normalize_project_name("https://github.com/FFmpeg/FFmpeg") == "ffmpeg/ffmpeg"
    assert normalize_project_name("github.com/torvalds/linux/") == "torvalds/linux"
    assert normalize_project_name("ffmpeg/ffmpeg.git") == "ffmpeg/ffmpeg"
    assert normalize_project_name("  https://github.com/php/php-src.git  ") == "php/php-src"


def test_known_project_aliases_manual_only():
    assert normalize_project_name("php") == "php/php-src"
    assert normalize_project_name("PHP") == "php/php-src"
    assert normalize_project_name("  php  ") == "php/php-src"
    assert normalize_project_name("torvalds/linux") == "torvalds/linux"


def test_missing_project_name():
    assert pd.isna(normalize_project_name(None))
    assert pd.isna(normalize_project_name(float("nan")))
    assert pd.isna(normalize_project_name(pd.NA))
    assert pd.isna(normalize_project_name(""))


def test_add_normalized_column_preserves_original():
    df = pd.DataFrame(
        {
            "project": ["FFmpeg", "php", "https://github.com/torvalds/linux.git"],
        }
    )

    result = add_normalized_project_column(df)

    assert result["project"].tolist() == ["FFmpeg", "php", "https://github.com/torvalds/linux.git"]
    assert result["project_normalized"].tolist() == [
        "ffmpeg",
        "php/php-src",
        "torvalds/linux",
    ]
    assert "project_normalized" not in df.columns


def test_find_shared_commit_project_names():
    df = pd.DataFrame(
        {
            "commit": ["abc", "abc", "xyz"],
            "project": ["linux", "torvalds/linux", "ffmpeg"],
        }
    )

    result = find_shared_commit_project_names(df)

    assert set(result["commit"]) == {"abc"}
    assert set(result["project"]) == {"linux", "torvalds/linux"}
    assert result["commit"].tolist() == sorted(result["commit"].tolist())


def test_find_shared_commit_empty():
    df = pd.DataFrame(
        {
            "commit": ["a1", "b2", "c3"],
            "project": ["p1", "p2", "p3"],
        }
    )
    result = find_shared_commit_project_names(df)
    assert result.empty
