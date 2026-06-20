from dagster import Definitions, EnvVar

from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource

_r2 = R2Resource(
    account_id=EnvVar("CLOUDFLARE_ACCOUNT_ID"),
    access_key_id=EnvVar("CLOUDFLARE_R2_ACCESS_KEY_ID"),
    secret_access_key=EnvVar("CLOUDFLARE_R2_SECRET_ACCESS_KEY"),
)

_duckdb = DuckDBR2Resource(
    account_id=EnvVar("CLOUDFLARE_ACCOUNT_ID"),
    access_key_id=EnvVar("CLOUDFLARE_R2_ACCESS_KEY_ID"),
    secret_access_key=EnvVar("CLOUDFLARE_R2_SECRET_ACCESS_KEY"),
)

defs = Definitions(
    assets=[],
    resources={
        "r2": _r2,
        "duckdb": _duckdb,
    },
)
