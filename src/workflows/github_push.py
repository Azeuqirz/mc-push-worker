"""Workflow: push files to a GitHub repository via the REST API."""

from typing import List

from pydantic import BaseModel

import mistralai.workflows as workflows


class FileToPush(BaseModel):
    path: str
    content: str
    encoding: str = "utf-8"  # "utf-8" (text) or "base64" (binary)


class PushInput(BaseModel):
    owner: str
    repo: str
    branch: str = "main"
    message: str
    files: List[FileToPush]


class PushResult(BaseModel):
    ok: bool
    commit_sha: str = ""
    detail: str = ""


@workflows.activity()
async def push_to_github(inp: PushInput) -> PushResult:
    # Imports live inside the activity: activities run outside the
    # deterministic workflow sandbox, which forbids these modules.
    import os
    import httpx

    token = (os.environ.get("GITHUB_TOKEN")
             or os.environ.get("github_token")
             or os.environ.get("GH_TOKEN"))
    if not token:
        return PushResult(ok=False, detail="No GitHub token found in environment (GITHUB_TOKEN / github_token / GH_TOKEN)")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    base = f"https://api.github.com/repos/{inp.owner}/{inp.repo}"
    async with httpx.AsyncClient(headers=headers, timeout=60) as c:
        r = await c.get(f"{base}/git/ref/heads/{inp.branch}")
        if r.status_code == 404:
            rb = await c.get(f"{base}")
            rb.raise_for_status()
            default_branch = rb.json()["default_branch"]
            rdef = await c.get(f"{base}/git/ref/heads/{default_branch}")
            rdef.raise_for_status()
            parent_sha = rdef.json()["object"]["sha"]
            rc = await c.post(f"{base}/git/refs", json={
                "ref": f"refs/heads/{inp.branch}", "sha": parent_sha})
            if rc.status_code not in (201, 422):
                return PushResult(ok=False, detail=f"create branch failed: {rc.status_code} {rc.text}")
        else:
            r.raise_for_status()
            parent_sha = r.json()["object"]["sha"]

        rc_ = await c.get(f"{base}/git/commits/{parent_sha}")
        rc_.raise_for_status()
        base_tree = rc_.json()["tree"]["sha"]

        tree_items = []
        for f in inp.files:
            enc = (f.encoding or "utf-8").lower()
            if enc not in ("utf-8", "base64"):
                return PushResult(ok=False, detail=f"unsupported encoding for {f.path}: {enc}")
            rb = await c.post(f"{base}/git/blobs", json={
                "content": f.content, "encoding": enc})
            rb.raise_for_status()
            tree_items.append({"path": f.path, "mode": "100644", "type": "blob",
                               "sha": rb.json()["sha"]})

        rt = await c.post(f"{base}/git/trees", json={
            "base_tree": base_tree, "tree": tree_items})
        rt.raise_for_status()
        new_tree = rt.json()["sha"]

        rco = await c.post(f"{base}/git/commits", json={
            "message": inp.message, "tree": new_tree, "parents": [parent_sha]})
        rco.raise_for_status()
        new_commit = rco.json()["sha"]

        ru = await c.patch(f"{base}/git/refs/heads/{inp.branch}",
                           json={"sha": new_commit, "force": False})
        ru.raise_for_status()

        return PushResult(ok=True, commit_sha=new_commit,
                          detail=f"pushed {len(inp.files)} file(s) to {inp.branch}")


@workflows.workflow.define(
    name="github-push",
    workflow_display_name="GitHub Push",
    workflow_description="Push one or more files (text or base64 binary) to a GitHub repository in a single commit.",
)
class GithubPushWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: PushInput) -> PushResult:
        return await push_to_github(input)
