import pandas as pd

from shield_core.datasets.project_normalization import (
    add_normalized_project_column,
    find_shared_commit_project_names,
    normalize_project_name,
)


def test_project_names_are_lowercase():
    assert normalize_project_name("FFmpeg") == "ffmpeg"
    assert normalize_project_name("ANDROID") == "android"


def test_project_name_whitespace_and_slashes():
    assert normalize_project_name("  FFmpeg  ") == "ffmpeg"
    assert normalize_project_name(r"torvalds\linux") == "torvalds/linux"


def test_known_project_aliases():
    assert normalize_project_name("linux") == "torvalds/linux"
    assert normalize_project_name("torvalds/linux") == "torvalds/linux"


def test_missing_project_name():
    assert pd.isna(normalize_project_name(None))
    assert pd.isna(normalize_project_name(float("nan")))


def test_add_normalized_column_preserves_original():
    df = pd.DataFrame(
        {
            "project": ["FFmpeg", "linux"],
        }
    )

    result = add_normalized_project_column(df)

    assert result["project"].tolist() == ["FFmpeg", "linux"]
    assert result["project_normalized"].tolist() == [
        "ffmpeg",
        "torvalds/linux",
    ]


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
