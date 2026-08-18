import os
import time
import uuid

from pathlib import Path


DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_POLL_SECONDS = 0.05
DEFAULT_STALE_SECONDS = 30.0

WINDOWS_RETRY_ATTEMPTS = 40
WINDOWS_RETRY_DELAY_SECONDS = 0.025


def replace_with_retry(
    source,
    destination,
    attempts=WINDOWS_RETRY_ATTEMPTS,
    delay_seconds=WINDOWS_RETRY_DELAY_SECONDS,
):

    source = Path(
        source
    )

    destination = Path(
        destination
    )

    for attempt in range(
        attempts
    ):

        try:

            os.replace(
                source,
                destination,
            )

            return True

        except PermissionError:

            if attempt == attempts - 1:

                raise

            time.sleep(
                delay_seconds
            )

    return False


class FileLock:

    def __init__(
        self,
        path,
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        poll_seconds=DEFAULT_POLL_SECONDS,
        stale_seconds=DEFAULT_STALE_SECONDS,
    ):

        self.path = Path(
            path
        )

        self.timeout_seconds = float(
            timeout_seconds
        )

        self.poll_seconds = float(
            poll_seconds
        )

        self.stale_seconds = float(
            stale_seconds
        )

        self.acquired = False

        self.owner_token = (
            f"{os.getpid()}-"
            f"{uuid.uuid4().hex}"
        )

    # ========================================================
    # READ CURRENT LOCK OWNER
    # ========================================================

    def _read_owner_token(
        self,
    ):

        try:

            text = self.path.read_text(
                encoding="utf-8"
            )

        except FileNotFoundError:

            return None

        except (
            PermissionError,
            OSError,
        ):

            return None

        for line in text.splitlines():

            if line.startswith(
                "owner="
            ):

                return line.split(
                    "=",
                    1,
                )[1].strip()

        return None

    # ========================================================
    # REMOVE ONLY IF THIS PROCESS STILL OWNS THE LOCK
    #
    # This prevents a retry from deleting a lock created later
    # by another process.
    # ========================================================

    def _remove_if_owned(
        self,
    ):

        for attempt in range(
            WINDOWS_RETRY_ATTEMPTS
        ):

            if not self.path.exists():

                return True

            current_owner = (
                self._read_owner_token()
            )

            if (
                current_owner
                != self.owner_token
            ):

                # The lock belongs to somebody else now.
                # Never delete it.
                return False

            try:

                self.path.unlink()

                return True

            except FileNotFoundError:

                return True

            except PermissionError:

                if (
                    attempt
                    == WINDOWS_RETRY_ATTEMPTS - 1
                ):

                    raise

                time.sleep(
                    WINDOWS_RETRY_DELAY_SECONDS
                )

        return False

    # ========================================================
    # STALE LOCK REMOVAL
    #
    # Re-check age immediately before deletion.
    # Never use the owner's normal release retry logic here.
    # ========================================================

    def _remove_stale_lock(
        self,
    ):

        try:

            stat = self.path.stat()

        except FileNotFoundError:

            return

        except OSError:

            return

        age = (
            time.time()
            - stat.st_mtime
        )

        if age <= self.stale_seconds:

            return

        # Capture identity of the stale lock.
        stale_owner = (
            self._read_owner_token()
        )

        try:

            # Re-check immediately before removing it.
            stat_again = self.path.stat()

        except FileNotFoundError:

            return

        except OSError:

            return

        age_again = (
            time.time()
            - stat_again.st_mtime
        )

        if age_again <= self.stale_seconds:

            return

        # If owner changed between checks,
        # it is not the stale lock we inspected.
        owner_again = (
            self._read_owner_token()
        )

        if owner_again != stale_owner:

            return

        try:

            self.path.unlink()

        except FileNotFoundError:

            pass

        except PermissionError:

            # Do not aggressively retry stale deletion.
            # Another process may be interacting with it.
            pass

        except OSError:

            pass

    # ========================================================
    # ACQUIRE
    # ========================================================

    def acquire(
        self,
    ):

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        deadline = (
            time.monotonic()
            + self.timeout_seconds
        )

        while True:

            self._remove_stale_lock()

            try:

                fd = os.open(
                    str(
                        self.path
                    ),
                    os.O_CREAT
                    | os.O_EXCL
                    | os.O_WRONLY,
                )

                try:

                    with os.fdopen(
                        fd,
                        "w",
                        encoding="utf-8",
                    ) as file:

                        file.write(
                            f"owner="
                            f"{self.owner_token}\n"
                        )

                        file.write(
                            f"pid="
                            f"{os.getpid()}\n"
                        )

                        file.write(
                            f"time="
                            f"{time.time()}\n"
                        )

                        file.flush()

                        os.fsync(
                            file.fileno()
                        )

                except Exception:

                    try:

                        os.close(
                            fd
                        )

                    except OSError:

                        pass

                    raise

                self.acquired = True

                return self

            except FileExistsError:

                if (
                    time.monotonic()
                    >= deadline
                ):

                    raise TimeoutError(
                        "Timed out waiting for lock: "
                        f"{self.path}"
                    )

                time.sleep(
                    self.poll_seconds
                )

            except PermissionError:

                if (
                    time.monotonic()
                    >= deadline
                ):

                    raise

                time.sleep(
                    self.poll_seconds
                )

    # ========================================================
    # RELEASE
    # ========================================================

    def release(
        self,
    ):

        if not self.acquired:

            return

        try:

            self._remove_if_owned()

        finally:

            self.acquired = False

    def __enter__(
        self,
    ):

        return self.acquire()

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):

        self.release()

        return False