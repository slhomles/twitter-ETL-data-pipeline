"""Project-specific exceptions."""


class StylePipelineError(RuntimeError):
    """Base class for expected pipeline failures."""


class RightsGateError(StylePipelineError):
    """Raised when a requested use is not approved by the rights manifest."""


class DataValidationError(StylePipelineError):
    """Raised when source data fails the required data contract."""


class OptionalDependencyError(StylePipelineError):
    """Raised when an optional feature is used without its dependency group."""
