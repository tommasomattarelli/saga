"""Migration failures that are safe to show to an operator or a log line."""


class MigrationError(RuntimeError):
    """Base class for expected, sanitized migration failures."""


class MigrationConfigurationError(MigrationError):
    pass


class MigrationLockTimeoutError(MigrationError):
    pass


class UnversionedSchemaError(MigrationError):
    pass


class UnknownRevisionError(MigrationError):
    pass


class SchemaMismatchError(MigrationError):
    def __init__(self, profile: str, differences: list[str]) -> None:
        self.profile = profile
        self.differences = differences
        shown = differences[:20]
        suffix = (
            "" if len(differences) <= len(shown) else f" (+{len(differences) - len(shown)} more)"
        )
        super().__init__(
            f"database does not match frozen profile {profile}: " + "; ".join(shown) + suffix
        )


class AlreadyVersionedError(MigrationError):
    pass
