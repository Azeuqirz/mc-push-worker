"""Workflow: push files to a GitHub repository via the REST API."""

import os
from typing import List

import httpx
from pydantic import BaseModel

import mistralai.workflows as workflows


class FileToPush(BaseModel):
    path: str
    content: str


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


def _headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN environment variable is not set")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


@workflows.activity()
async def push_to_github(inp: PushInput) -> PushResult:
    base = f"https://api.github.com/repos/{inp.owner}/{inp.repo}"
    async with httpx.AsyncClient(headers=_headers(), timeout=60) as c:
        # 1. Resolve the branch head (fall back to default branch if missing)
        r = await c.get(f"{base}/git/ref/heads/{inp.branch}")
        if r.status_code == 404:
            rb = await c.get(f"{base}")
            rb.raise_for_status()
            default_branch = rb.json()["default_branch"]
            rdef = await c.get(f"{base}/git/ref/heads/{default_branch}")
            rdef.raise_for_status()
            parent_sha = rdef.json()["object"]["sha"]
            created_ref = False
        else:
            r.raise_for_status()
            parent_sha = r.json()["object"]["sha"]
            created_ref = True
        if not created_ref:
            # create the branch at the default branch head
            rc = await c.post(f"{base}/git/refs", json={
                "ref": f"refs/heads/{inp.branch}", "sha": parent_sha})
            if rc.status_code not in (201, 422):
                return PushResult(ok=False, detail=f"create branch failed: {rc.status_code} {rc.text}")

        # 2. Base tree
        rc_ = await c.get(f"{base}/git/commits/{parent_sha}")
        rc_.raise_for_status()
        base_tree = rc_.json()["tree"]["sha"]

        # 3. Blobs
        tree_items = []
        for f in inp.files:
            rb = await c.post(f"{base}/git/blobs", json={
                "content": f.content, "encoding": "utf-8"})
            rb.raise_for_status()
            tree_items.append({"path": f.path, "mode": "100644", "type": "blob",
                               "sha": rb.json()["sha"]})

        # 4. Tree
        rt = await c.post(f"{base}/git/trees", json={
            "base_tree": base_tree, "tree": tree_items})
        rt.raise_for_status()
        new_tree = rt.json()["sha"]

        # 5. Commit
        rco = await c.post(f"{base}/git/commits", json={
            "message": inp.message, "tree": new_tree, "parents": [parent_sha]})
        rco.raise_for_status()
        new_commit = rco.json()["sha"]

        # 6. Update ref
        ru = await c.patch(f"{base}/git/refs/heads/{inp.branch}",
                           json={"sha": new_commit, "force": False})
        ru.raise_for_status()

        return PushResult(ok=True, commit_sha=new_commit,
                          detail=f"pushed {len(inp.files)} file(s) to {inp.branch}")


@workflows.workflow.define(
    name="github-push",
    workflow_display_name="GitHub Push",
    workflow_description="Push one or more files to a GitHub repository in a single commit.",
)
class GithubPushWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: PushInput) -> PushResult:
        return await push_to_github(input)
