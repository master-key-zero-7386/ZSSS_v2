

from sp_api.base.marketplaces import Marketplaces
from sp_api.base.credential_provider import CredentialProvider
import json

print("\n=== 【Marketplaces 一覧】 ===")
mp_all = {
    k: {
        "marketplace_id": v.marketplace_id,
        "endpoint": v.endpoint,
        "region": v.region,
    }
    for k, v in Marketplaces.__members__.items()
}
print(json.dumps(mp_all, ensure_ascii=False, indent=2))

print("\n=== 【CredentialProvider 内部構造】 ===")
print(CredentialProvider.__init__.__code__.co_varnames)
