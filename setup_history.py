import csv
import os
import tempfile
import time

from pathlib import Path

from state_lock import (
    FileLock,
    replace_with_retry,
)


STATE_DIR = Path("state")

HISTORY_FILE = (
    STATE_DIR
    / "setup_history.csv"
)

HISTORY_LOCK_FILE = (
    STATE_DIR
    / "setup_history.lock"
)


COLUMNS = [
    "setup_id",
    "contract_id",
    "contract_name",
    "side",
    "final_stage",
    "key_level",
    "c1_time",
    "c2_time",
    "c3_time",
    "c4_time",
    "c5_time",
    "terminal_time",
    "terminal_reason",
    "created_at",
    "updated_at",
]


def _ensure_state_dir():

    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def _read_rows(
    attempts=40,
    delay_seconds=0.025,
):

    _ensure_state_dir()

    if not HISTORY_FILE.exists():

        return []

    last_error = None

    for attempt in range(
        attempts
    ):

        try:

            with HISTORY_FILE.open(
                "r",
                newline="",
                encoding="utf-8",
            ) as file:

                reader = csv.DictReader(
                    file
                )

                return list(
                    reader
                )

        except PermissionError as exc:

            last_error = exc

            if attempt == attempts - 1:

                raise

            time.sleep(
                delay_seconds
            )

        except FileNotFoundError:

            # The file may be in the tiny replacement window.
            #
            # Do NOT immediately interpret that as empty if
            # another process may be completing os.replace().
            if attempt == attempts - 1:

                if HISTORY_FILE.exists():

                    continue

                return []

            time.sleep(
                delay_seconds
            )

        except Exception:

            # Corrupt CSV, decoding problems, unexpected I/O,
            # etc. must propagate.
            #
            # Never silently transform them into [] because
            # archive_terminal_setup() could then overwrite
            # valid history and falsely report success.
            raise

    if last_error is not None:

        raise last_error

    raise RuntimeError(
        "Unable to read setup history."
    )


def _write_rows(
    rows,
):

    _ensure_state_dir()

    temp_path = None

    try:

        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            dir=STATE_DIR,
            prefix="setup_history_",
            suffix=".tmp",
            delete=False,
        ) as file:

            temp_path = Path(
                file.name
            )

            writer = csv.DictWriter(
                file,
                fieldnames=COLUMNS,
                extrasaction="ignore",
            )

            writer.writeheader()

            for row in rows:

                normalized = {
                    column:
                        row.get(
                            column,
                            ""
                        )
                    for column
                    in COLUMNS
                }

                writer.writerow(
                    normalized
                )

            file.flush()

            os.fsync(
                file.fileno()
            )

        replace_with_retry(
            temp_path,
            HISTORY_FILE,
        )

        temp_path = None

    finally:

        if (
            temp_path is not None
            and temp_path.exists()
        ):

            try:

                temp_path.unlink()

            except OSError:

                pass


def _ensure_schema():

    _ensure_state_dir()

    if not HISTORY_FILE.exists():

        _write_rows(
            []
        )

        return

    rows = _read_rows()

    try:

        with HISTORY_FILE.open(
            "r",
            newline="",
            encoding="utf-8",
        ) as file:

            reader = csv.reader(
                file
            )

            header = next(
                reader,
                [],
            )

    except Exception:

        header = []

    if header == COLUMNS:

        return

    # Existing/legacy rows are preserved.
    # Missing contract fields remain blank and are displayed
    # by recent_setups.py as LEGACY / UNBOUND.

    _write_rows(
        rows
    )


def _existing_setup_ids():

    _ensure_schema()

    ids = set()

    for row in _read_rows():

        setup_id = row.get(
            "setup_id"
        )

        if setup_id:

            ids.add(
                setup_id
            )

    return ids


def _valid_contract_binding(
    state,
):

    contract_id = state.get(
        "contract_id"
    )

    contract_name = state.get(
        "contract_name"
    )

    if contract_id is None:

        return False

    if contract_name is None:

        return False

    contract_id = str(
        contract_id
    ).strip()

    contract_name = str(
        contract_name
    ).strip()

    if not contract_id:

        return False

    if not contract_name:

        return False

    if contract_id.lower() in [
        "none",
        "nan",
    ]:

        return False

    if contract_name.lower() in [
        "none",
        "nan",
    ]:

        return False

    return True


def archive_terminal_setup(
    state,
):

    setup_id = state.get(
        "setup_id"
    )

    if not setup_id:

        return False

    stage = state.get(
        "stage"
    )

    if stage not in [
        "C5 CONFIRMED",
        "INVALIDATED",
    ]:

        return False

    # ========================================================
    # CONTRACT ENFORCEMENT
    #
    # Existing legacy rows remain untouched.
    # NEW terminal records MUST be contract-bound.
    # ========================================================

    if not _valid_contract_binding(
        state
    ):

        return False

    row = {
        "setup_id":
            setup_id,

        "contract_id":
            str(
                state.get(
                    "contract_id"
                )
            ),

        "contract_name":
            str(
                state.get(
                    "contract_name"
                )
            ),

        "side":
            state.get(
                "side"
            ),

        "final_stage":
            stage,

        "key_level":
            state.get(
                "key_level"
            ),

        "c1_time":
            state.get(
                "c1_time"
            ),

        "c2_time":
            state.get(
                "c2_time"
            ),

        "c3_time":
            state.get(
                "c3_time"
            ),

        "c4_time":
            state.get(
                "c4_time"
            ),

        "c5_time":
            state.get(
                "c5_time"
            ),

        "terminal_time":
            state.get(
                "terminal_time"
            ),

        "terminal_reason":
            state.get(
                "terminal_reason"
            ),

        "created_at":
            state.get(
                "created_at"
            ),

        "updated_at":
            state.get(
                "updated_at"
            ),
    }

    # ========================================================
    # CONCURRENT-SAFE TRANSACTION
    #
    # Lock covers schema check, dedupe check and final write.
    # ========================================================

    with FileLock(
        HISTORY_LOCK_FILE
    ):

        _ensure_schema()

        rows = _read_rows()

        existing_ids = {
            existing.get(
                "setup_id"
            )
            for existing
            in rows
            if existing.get(
                "setup_id"
            )
        }

        if setup_id in existing_ids:

            return False

        rows.append(
            row
        )

        _write_rows(
            rows
        )

    return True
