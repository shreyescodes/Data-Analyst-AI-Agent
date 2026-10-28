"""Exception hierarchy for the application.

Every error raised deliberately by the core package derives from
:class:`DataAgentError`, so the UI layer can show a friendly message for
expected failures while still letting genuine bugs surface.
"""


class DataAgentError(Exception):
    """Base class for all expected, user-facing errors."""


class ConfigurationError(DataAgentError):
    """An environment variable or setting has an invalid value."""


class IngestionError(DataAgentError):
    """A data source could not be read or produced no usable rows."""


class StorageError(DataAgentError):
    """The query store could not load data or execute a query."""


class QueryTimeoutError(StorageError):
    """A query ran longer than the configured time limit and was interrupted."""


class UnsafeQueryError(StorageError):
    """A SQL statement was rejected because it is not a read-only query."""


class ChartError(DataAgentError):
    """A chart could not be rendered from the given specification."""


class LLMError(DataAgentError):
    """The language-model provider returned an error or an unusable response."""


class LLMAuthenticationError(LLMError):
    """The language-model provider rejected the configured API key."""


class VersioningError(DataAgentError):
    """A dataset snapshot could not be saved, found or verified."""
