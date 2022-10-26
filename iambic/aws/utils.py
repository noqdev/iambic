from enum import Enum

from iambic.core.utils import aio_wrapper


async def paginated_search(
    search_fnc, response_key: str, max_results: int = None, **search_kwargs
) -> list:
    """Retrieve and aggregate each paged response, returning a single list of each response object
    :param search_fnc:
    :param response_key:
    :param max_results:
    :return:
    """
    results = []

    while True:
        response = await aio_wrapper(search_fnc, **search_kwargs)
        results.extend(response.get(response_key, []))

        if not response["IsTruncated"] or (max_results and len(results) >= max_results):
            return results
        else:
            search_kwargs["Marker"] = response["Marker"]


class RegionName(Enum):
    us_east_1 = "us-east-1"
    us_west_1 = "us-west-1"
    us_west_2 = "us-west-2"
    eu_west_1 = "eu-west-1"
    eu_west_2 = "eu-west-2"
    eu_central_1 = "eu-central-1"
    ap_southeast_1 = "ap-southeast-1"
    ap_southeast_2 = "ap-southeast-2"
    ap_northeast_1 = "ap-northeast-1"
    ap_northeast_2 = "ap-northeast-2"
    sa_east_1 = "sa-east-1"
    cn_north_1 = "cn-north-1"