from noq_form.core.utils import aio_wrapper


async def paginated_search(search_fnc, response_key: str, max_results: int = None, **search_kwargs) -> list:
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
