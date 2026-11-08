from datetime import UTC, date, datetime

from orchestrator.backup import (
    RemoteFile,
    archive_files_to_delete,
    backup_days_to_delete,
    exclude_table_data_args,
)

GB = 1_000_000_000


def test_each_raw_chunk_pattern_becomes_one_exclude_argument() -> None:
    args = exclude_table_data_args(
        ["_timescaledb_internal._hyper_1_*", "_timescaledb_internal._hyper_2_*"]
    )
    assert args == [
        "--exclude-table-data=_timescaledb_internal._hyper_1_*",
        "--exclude-table-data=_timescaledb_internal._hyper_2_*",
    ]


def test_quotes_in_names_survive_as_one_argument() -> None:
    # pg_dump patterns treat a double-quoted name literally.
    assert exclude_table_data_args(['"odd schema"."t"']) == [
        '--exclude-table-data="odd schema"."t"'
    ]


def test_only_the_newest_days_of_backups_are_kept() -> None:
    days = [date(2026, 11, d) for d in (1, 5, 3, 2, 4)]
    assert backup_days_to_delete(days, keep=3) == [date(2026, 11, 1), date(2026, 11, 2)]


def test_nothing_is_deleted_while_under_the_keep_count() -> None:
    assert backup_days_to_delete([date(2026, 11, 1)], keep=14) == []


def _file(path: str, gb: float, day: int) -> RemoteFile:
    return RemoteFile(path=path, size=int(gb * GB), mod_time=datetime(2026, 10, day, tzinfo=UTC))


def test_archives_are_untouched_under_the_cap() -> None:
    files = [_file("a", 3, 1), _file("b", 3, 2)]
    assert archive_files_to_delete(files, other_bytes=1 * GB, cap_bytes=8 * GB) == []


def test_oldest_archives_go_first_until_under_the_cap() -> None:
    files = [_file("new", 3, 20), _file("oldest", 3, 1), _file("middle", 3, 10)]
    # 9 GB of archives + 0.5 GB of backups = 9.5 GB; dropping the oldest 3 GB gives 6.5 GB.
    assert archive_files_to_delete(files, other_bytes=GB // 2, cap_bytes=8 * GB) == ["oldest"]


def test_ties_on_time_are_broken_by_path_so_runs_agree() -> None:
    files = [_file("b", 5, 1), _file("a", 5, 1)]
    assert archive_files_to_delete(files, other_bytes=0, cap_bytes=8 * GB) == ["a"]


def test_backups_alone_over_the_cap_delete_every_archive_but_never_backups() -> None:
    files = [_file("a", 1, 1)]
    assert archive_files_to_delete(files, other_bytes=9 * GB, cap_bytes=8 * GB) == ["a"]
