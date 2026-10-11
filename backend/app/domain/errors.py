"""Domain errors. Raised by the core; mapped to HTTP status codes in app.api.errors."""


class DomainError(Exception):
    """Base class for every error the core raises on purpose."""


class CatalogNotInitializedError(DomainError):
    """An order or restock arrived before init_catalog."""


class CatalogAlreadyInitializedError(DomainError):
    """init_catalog was called a second time."""


class InvalidCatalogError(DomainError):
    """Empty catalog, duplicate product ids, or a mass <= 0 or > the package limit."""


class UnknownProductError(DomainError):
    """An order or restock referenced a product_id that is not in the catalog."""


class DuplicateOrderError(DomainError):
    """An order_id was reused with a different payload."""
