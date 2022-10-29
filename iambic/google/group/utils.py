from iambic.config.models import GoogleProject
from iambic.core.logger import log


async def list_groups(google_project: GoogleProject):
    try:
        service = await google_project.get_service_connection("admin", "directory_v1")
        if not service:
            return []
    except AttributeError as err:
        log.exception("Unable to process google groups.", error=err)
        return

    req = service.groups().list(domain=domain)  # TODO: Async
    res = req.execute()
    if res and "groups" in res:
        for group in res["groups"]:
            member_req = service.members().list(groupKey=group["email"])
            member_res = member_req.execute() or {}