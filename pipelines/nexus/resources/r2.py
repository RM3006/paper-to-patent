from dagster import ConfigurableResource


class R2Resource(ConfigurableResource):
    """Cloudflare R2 bucket coordinates.

    Passed to assets that write Parquet via DuckDB httpfs. The DuckDB secret
    itself is configured in DuckDBR2Resource — this resource holds the bucket
    name and account ID for path construction.
    """

    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket: str = "p2p-lake"
