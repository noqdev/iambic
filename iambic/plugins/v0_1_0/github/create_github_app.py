# https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest#examples

from __future__ import annotations

import os
import time
import webbrowser
from multiprocessing import Process

import aiohttp
import yaml
from aiohttp import web

from iambic.core.logger import log

routes = web.RouteTableDef()

LOCAL_ASSETS_DIR = f"{str(os.path.dirname(__file__))}/local_web_server_assets"
SAVE_DIR = "~/.iambic"
SECRETS_FULL_PATH = None


@routes.get("/")
async def index(request):
    return web.FileResponse(f"{LOCAL_ASSETS_DIR}/index.html")


@routes.get("/redirect")
async def redirect(request):
    ## here how to get query parameters
    code = request.rel_url.query["code"]
    # state = request.rel_url.query["state"]
    # result = f"code: {code}, state: {state}"
    await exchange_token(code)
    return web.FileResponse(f"{LOCAL_ASSETS_DIR}/success.html")


async def exchange_token(code):
    async with aiohttp.ClientSession("https://api.github.com/") as session:
        async with session.post(f"/app-manifests/{code}/conversions") as resp:
            payload = await resp.json()

    full_path = os.path.expanduser(SAVE_DIR)
    os.makedirs(full_path, exist_ok=True)
    full_path = f"{full_path}/.github_secrets.yaml"

    with open(full_path, "w") as f:
        yaml.dump(payload, f)

    SECRETS_FULL_PATH = full_path
    assert SECRETS_FULL_PATH


def run_local_webserver():
    app = web.Application()
    app.add_routes(routes)
    web.run_app(app, host="localhost", port=8080, print=False)


def has_github_app_secrets_locally():
    full_path = os.path.expanduser(SAVE_DIR)
    os.makedirs(full_path, exist_ok=True)
    full_path = f"{full_path}/.github_secrets.yaml"
    return os.path.exists(full_path)


def remove_github_app_secrets():
    full_path = os.path.expanduser(SAVE_DIR)
    os.makedirs(full_path, exist_ok=True)
    full_path = f"{full_path}/.github_secrets.yaml"
    if os.path.exists(full_path):
        os.remove(full_path)
        log.info(f"Remove local GitHub App secrets from {full_path}")


def get_github_app_secrets():
    full_path = os.path.expanduser(SAVE_DIR)
    os.makedirs(full_path, exist_ok=True)
    full_path = f"{full_path}/.github_secrets.yaml"

    if not os.path.exists(full_path):
        # create a process
        process = Process(target=run_local_webserver)
        # run the process
        process.start()

        # wait for the process to finish
        localhost_url = "http://localhost:8080/"
        # hack to wait for the http process to be ready.
        time.sleep(5)
        webbrowser.open(localhost_url, new=0, autoraise=True)
        log.info(f"Open a browser to {localhost_url} and follow instructions there")

        start_time = time.time()
        while time.time() - start_time < 3000:
            if os.path.exists(full_path):
                process.kill()
                break
            else:
                time.sleep(10)

    with open(full_path, "r") as f:
        github_app_secrets = yaml.safe_load(f)
    return github_app_secrets


if __name__ == "__main__":
    run_local_webserver()
