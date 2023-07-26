# https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest#examples

from __future__ import annotations

import aiohttp
import yaml
from aiohttp import web

routes = web.RouteTableDef()

# @routes.get('/')
# async def hello(request):
#     return web.Response(text="Hello, world")


@routes.get("/")
async def index(request):
    return web.FileResponse("./index.html")


@routes.get("/redirect")
async def redirect(request):
    ## here how to get query parameters
    code = request.rel_url.query["code"]
    state = request.rel_url.query["state"]
    result = f"code: {code}, state: {state}"
    print(result)
    await exchange_token(code)
    return web.FileResponse("./success.html")


async def exchange_token(code):
    async with aiohttp.ClientSession("https://api.github.com/") as session:
        async with session.post(f"/app-manifests/{code}/conversions") as resp:
            print(resp.status)
            payload = await resp.json()
    dot_env = {
        "webhook_secret": payload["webhook_secret"],
        "pem": payload["pem"],
    }
    with open(".env", "w") as f:
        yaml.dump(dot_env, f)


app = web.Application()
app.add_routes(routes)
web.run_app(app)
