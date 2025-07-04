import os
import sys
from fastmcp import FastMCP
from github import Github, Auth, GithubException, InputFileContent
from datetime import datetime

# Initialize FastMCP server
mcp = FastMCP("GitHub Manager Full")

# --- GitHub API Initialization ---
github_token = os.environ.get("GITHUB_TOKEN")
if not github_token:
    print("GITHUB_TOKEN environment variable not set. GitHub tools will not function.", file=sys.stderr)
    g = None
else:
    try:
        auth = Auth.Token(github_token)
        g = Github(auth=auth)
        # Test authentication to catch errors early
        g.get_user().login # This will raise an exception if the token is invalid
        print("GitHub API client initialized successfully.", file=sys.stderr)
    except Exception as e:
        g = None
        print(f"Error initializing GitHub API client: {e}. Please check your GITHUB_TOKEN.", file=sys.stderr)


# --- Utility Function for Repository Access ---
def _get_repo_safe(repo_full_name: str):
    """Helper to safely get a repository object, handling errors."""
    if not g:
        raise ValueError("GitHub token is not configured or invalid. Please set GITHUB_TOKEN environment variable correctly.")
    try:
        # Try getting by full name first (owner/repo)
        return g.get_repo(repo_full_name)
    except GithubException as e:
        raise ValueError(f"Could not find repository '{repo_full_name}'. Error: {e.data}")


# --- Core MCP Tools ---

@mcp.tool()
def list_issues(repo_full_name: str, state: str = "open", limit: int = 5, assignee_username: str = None) -> list[dict]:
    """
    Lists issues for a specified GitHub repository. Defaults to open issues.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        state (str): The state of issues to list ('open', 'closed', 'all'). Defaults to 'open'.
        limit (int): Maximum number of issues to return. Defaults to 5.
        assignee_username (str, optional): Filter issues by a specific assignee's username.
    Returns:
        list[dict]: A list of dictionaries, each representing an issue with 'title', 'number', 'url', 'state', 'created_at', 'assignees'.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        filters = {'state': state}
        if assignee_username:
            assignee_user = g.get_user(assignee_username)
            filters['assignee'] = assignee_user

        issues = repo.get_issues(**filters)
        results = []
        for i, issue in enumerate(issues):
            if i >= limit: break
            assignees_list = [a.login for a in issue.assignees] if issue.assignees else []
            results.append({
                "title": issue.title,
                "number": issue.number,
                "url": issue.html_url,
                "state": issue.state,
                "created_at": issue.created_at.isoformat(),
                "assignees": assignees_list
            })
        return results
    except (ValueError, GithubException) as e:
        return {"error": str(e)}


@mcp.tool()
def create_github_issue(repo_full_name: str, title: str, body: str = "", assignee_username: str = None, labels: list[str] = None) -> dict:
    """
    Creates a new issue in a specified GitHub repository.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        title (str): The title of the new issue.
        body (str): The body/description of the issue.
        assignee_username (str, optional): The GitHub username to assign the issue to.
        labels (list[str], optional): A list of label names to apply to the issue.
    Returns:
        dict: Details of the created issue or an error message.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        assignees = [g.get_user(assignee_username)] if assignee_username else []
        issue = repo.create_issue(title=title, body=body, assignees=assignees, labels=labels if labels else [])
        return {"message": "Issue created successfully!", "title": issue.title, "number": issue.number, "url": issue.html_url}
    except (ValueError, GithubException) as e:
        return {"error": str(e)}


@mcp.tool()
def get_pull_request_summary(repo_full_name: str, pr_number: int) -> dict:
    """
    Gets a detailed summary of a specific pull request.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        pr_number (int): The number of the pull request.
    Returns:
        dict: Detailed summary of the PR or an error message.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        pr = repo.get_pull(pr_number)
        return {
            "title": pr.title,
            "number": pr.number,
            "state": pr.state,
            "creator": pr.user.login,
            "url": pr.html_url,
            "merged": pr.merged,
            "mergeable": pr.mergeable,
            "commits_count": pr.commits,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "changed_files_count": pr.changed_files,
            "base_branch": pr.base.ref,
            "head_branch": pr.head.ref,
            "body": pr.body # Include PR body for context
        }
    except (ValueError, GithubException) as e:
        return {"error": f"Could not retrieve PR summary. Check repo name or PR number. Error: {e}"}


@mcp.tool()
def list_branches(repo_full_name: str, protected_only: bool = False, limit: int = 10) -> list[dict]:
    """
    Lists branches for a specified GitHub repository.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        protected_only (bool): If True, only lists protected branches. Defaults to False.
        limit (int): Maximum number of branches to return. Defaults to 10.
    Returns:
        list[dict]: A list of dictionaries, each with 'name' and 'protected' status of the branch.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        branches = repo.get_branches()
        results = []
        for i, branch in enumerate(branches):
            if i >= limit: break
            if not protected_only or branch.protected:
                results.append({
                    "name": branch.name,
                    "protected": branch.protected
                })
        return results
    except (ValueError, GithubException) as e:
        return {"error": str(e)}


@mcp.tool()
def get_file_content_from_repo(repo_full_name: str, path: str, ref: str = None) -> dict:
    """
    Retrieves the content of a file from a specified GitHub repository.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        path (str): The path to the file within the repository (e.g., "src/main.py").
        ref (str, optional): The name of the commit/branch/tag. Defaults to the default branch.
    Returns:
        dict: A dictionary containing 'content' (decoded), 'encoding', and 'sha' or an error.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        contents = repo.get_contents(path, ref=ref)
        if isinstance(contents, list): # It's a directory
            return {"error": f"Path '{path}' is a directory, not a file."}

        return {
            "content": contents.decoded_content.decode('utf-8'),
            "encoding": contents.encoding,
            "sha": contents.sha
        }
    except (ValueError, GithubException) as e:
        return {"error": f"Could not retrieve file content. Check repo, path, or ref. Error: {e}"}


@mcp.tool()
def create_or_update_file(repo_full_name: str, path: str, message: str, content: str, branch: str = None, sha: str = None) -> dict:
    """
    Creates a new file or updates an existing file in a GitHub repository.
    Requires 'Contents (write)' permission on your PAT.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        path (str): The path to the file within the repository (e.g., "docs/new_doc.md").
        message (str): The commit message for the file operation.
        content (str): The new content for the file.
        branch (str, optional): The branch to perform the operation on. Defaults to the default branch.
        sha (str, optional): The SHA of the file blob if updating an existing file (required for updates).
    Returns:
        dict: Details of the commit and file, or an error.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        if sha: # Update existing file
            response = repo.update_file(path, message, content, sha, branch=branch)
        else: # Create new file
            response = repo.create_file(path, message, content, branch=branch)

        return {
            "message": "File operation successful!",
            "commit_sha": response['commit'].sha,
            "file_path": response['content'].path,
            "file_url": response['content'].html_url
        }
    except (ValueError, GithubException) as e:
        return {"error": f"Could not create/update file. Check permissions, path, or SHA. Error: {e}"}


@mcp.tool()
def create_pull_request(repo_full_name: str, title: str, head: str, base: str, body: str = None, draft: bool = False) -> dict:
    """
    Creates a new pull request in a specified GitHub repository.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        title (str): The title of the pull request.
        head (str): The name of the branch where your changes are implemented (e.g., "feature/my-new-feature").
        base (str): The name of the branch you want to merge your changes into (e.g., "main").
        body (str, optional): The description of the pull request.
        draft (bool, optional): Whether to create a draft pull request. Defaults to False.
    Returns:
        dict: Details of the created pull request or an error message.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        pull = repo.create_pull(title=title, head=head, base=base, body=body, draft=draft)
        return {
            "message": "Pull request created successfully!",
            "title": pull.title,
            "number": pull.number,
            "url": pull.html_url,
            "state": pull.state
        }
    except (ValueError, GithubException) as e:
        return {"error": str(e)}


@mcp.tool()
def merge_pull_request(repo_full_name: str, pr_number: int, commit_message: str = None, sha: str = None, merge_method: str = "merge") -> dict:
    """
    Merges a pull request in a specified GitHub repository.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        pr_number (int): The number of the pull request to merge.
        commit_message (str, optional): The commit message for the merge.
        sha (str, optional): SHA that pull request head must match to allow merge.
        merge_method (str, optional): Merge method to use. Can be 'merge', 'squash', or 'rebase'. Defaults to 'merge'.
    Returns:
        dict: Details of the merge operation or an error message.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        pr = repo.get_pull(pr_number)
        if not pr.mergeable:
            return {"error": f"Pull request #{pr_number} is not mergeable."}

        merge_result = pr.merge(commit_message=commit_message, sha=sha, merge_method=merge_method)
        return {
            "message": merge_result.message,
            "merged": merge_result.merged,
            "sha": merge_result.sha,
            "url": pr.html_url
        }
    except (ValueError, GithubException) as e:
        return {"error": str(e)}


@mcp.tool()
def add_pull_request_review_comment(repo_full_name: str, pr_number: int, body: str, commit_id: str, path: str, position: int) -> dict:
    """
    Adds a review comment to a specific line in a pull request.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        pr_number (int): The number of the pull request.
        body (str): The text of the comment.
        commit_id (str): The SHA of the commit being commented on.
        path (str): The file path relative to the repository.
        position (int): The line index in the diff to comment on.
    Returns:
        dict: Details of the created comment or an error message.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        pr = repo.get_pull(pr_number)
        commit = repo.get_commit(commit_id)
        comment = pr.create_review_comment(body=body, commit_id=commit.sha, path=path, position=position)
        return {
            "message": "Review comment added successfully!",
            "id": comment.id,
            "url": comment.html_url
        }
    except (ValueError, GithubException) as e:
        return {"error": str(e)}


@mcp.tool()
def request_pull_request_review(repo_full_name: str, pr_number: int, reviewers: list[str] = None, team_reviewers: list[str] = None) -> dict:
    """
    Requests reviews for a pull request from specific users or teams.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        pr_number (int): The number of the pull request.
        reviewers (list[str], optional): A list of usernames to request review from.
        team_reviewers (list[str], optional): A list of team slugs to request review from.
    Returns:
        dict: Confirmation message or an error.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        pr = repo.get_pull(pr_number)
        pr.create_review_request(reviewers=reviewers, team_reviewers=team_reviewers)
        return {"message": "Review request sent successfully!"}
    except (ValueError, GithubException) as e:
        return {"error": str(e)}


@mcp.tool()
def list_repository_contents(repo_full_name: str, path: str = "", ref: str = None) -> list[dict]:
    """
    Lists files and directories at a given path in a GitHub repository.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        path (str, optional): The path within the repository to list contents for. Defaults to root "".
        ref (str, optional): The name of the commit/branch/tag. Defaults to the default branch.
    Returns:
        list[dict]: A list of dictionaries, each representing a file or directory with 'name', 'path', 'type' ('file' or 'dir'), and 'url'.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        contents = repo.get_contents(path, ref=ref)
        results = []
        if isinstance(contents, list):
            for content in contents:
                results.append({
                    "name": content.name,
                    "path": content.path,
                    "type": content.type,
                    "url": content.html_url
                })
        else: # Single file content when path points directly to a file
            results.append({
                "name": contents.name,
                "path": contents.path,
                "type": contents.type,
                "url": contents.html_url
            })
        return results
    except (ValueError, GithubException) as e:
        return {"error": f"Could not list repository contents. Check repo, path, or ref. Error: {e}"}


@mcp.tool()
def delete_file(repo_full_name: str, path: str, message: str, sha: str, branch: str = None) -> dict:
    """
    Deletes a file from a GitHub repository.
    Requires 'Contents (write)' permission on your PAT.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        path (str): The path to the file within the repository (e.g., "old_file.txt").
        message (str): The commit message for the deletion.
        sha (str): The SHA of the file to delete. (Get this from get_file_content_from_repo).
        branch (str, optional): The branch to perform the operation on. Defaults to the default branch.
    Returns:
        dict: Details of the commit or an error.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        response = repo.delete_file(path, message, sha, branch=branch)
        return {
            "message": "File deleted successfully!",
            "commit_sha": response['commit'].sha,
            "file_path": path
        }
    except (ValueError, GithubException) as e:
        return {"error": f"Could not delete file. Check permissions, path, or SHA. Error: {e}"}


@mcp.tool()
def list_releases(repo_full_name: str, limit: int = 5) -> list[dict]:
    """
    Lists releases for a specified GitHub repository.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        limit (int): Maximum number of releases to return. Defaults to 5.
    Returns:
        list[dict]: A list of dictionaries, each representing a release with 'tag_name', 'name', 'url', 'created_at', 'published_at', 'prerelease', 'draft'.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        releases = repo.get_releases()
        results = []
        for i, release in enumerate(releases):
            if i >= limit: break
            results.append({
                "tag_name": release.tag_name,
                "name": release.title,
                "url": release.html_url,
                "created_at": release.created_at.isoformat(),
                "published_at": release.published_at.isoformat() if release.published_at else None,
                "prerelease": release.prerelease,
                "draft": release.draft
            })
        return results
    except (ValueError, GithubException) as e:
        return {"error": str(e)}


@mcp.tool()
def create_release(repo_full_name: str, tag_name: str, name: str = None, body: str = None, draft: bool = False, prerelease: bool = False, target_commitish: str = None) -> dict:
    """
    Creates a new release in a specified GitHub repository.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        tag_name (str): The name of the tag.
        name (str, optional): The name of the release. Defaults to tag_name.
        body (str, optional): Text describing the contents of the tag.
        draft (bool, optional): True to create a draft (unpublished) release. Defaults to False.
        prerelease (bool, optional): True to identify the release as a prerelease. Defaults to False.
        target_commitish (str, optional): Specifies the commitish value that determines where the Git tag is created. Can be a branch name or a commit SHA. Defaults to the repository's default branch.
    Returns:
        dict: Details of the created release or an error.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        release = repo.create_git_release(
            tag=tag_name,
            name=name if name else tag_name,
            message=body,
            draft=draft,
            prerelease=prerelease,
            target_commitish=target_commitish
        )
        return {
            "message": "Release created successfully!",
            "tag_name": release.tag_name,
            "name": release.title,
            "url": release.html_url
        }
    except (ValueError, GithubException) as e:
        return {"error": str(e)}


@mcp.tool()
def list_workflows(repo_full_name: str, limit: int = 5) -> list[dict]:
    """
    Lists GitHub Actions workflows for a specified repository.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        limit (int): Maximum number of workflows to return. Defaults to 5.
    Returns:
        list[dict]: A list of dictionaries, each representing a workflow with 'name', 'id', 'state', 'path', 'url'.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        workflows = repo.get_workflows()
        results = []
        for i, workflow in enumerate(workflows):
            if i >= limit: break
            results.append({
                "name": workflow.name,
                "id": workflow.id,
                "state": workflow.state,
                "path": workflow.path,
                "url": workflow.html_url
            })
        return results
    except (ValueError, GithubException) as e:
        return {"error": str(e)}


@mcp.tool()
def trigger_workflow(repo_full_name: str, workflow_id_or_name: str, ref: str, inputs: dict = None) -> dict:
    """
    Triggers a GitHub Actions workflow dispatch event.
    Requires 'Workflows (write)' permission on your PAT.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        workflow_id_or_name (str): The ID or file name of the workflow to trigger (e.g., "build.yml" or 123456).
        ref (str): The git ref (e.g., branch, tag, or SHA) to trigger the workflow on.
        inputs (dict, optional): Inputs to pass to the workflow.
    Returns:
        dict: Confirmation of workflow dispatch or an error.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        if isinstance(workflow_id_or_name, int):
            workflow = repo.get_workflow(workflow_id_or_name)
        else:
            workflow = repo.get_workflow(workflow_id_or_name)

        workflow.create_dispatch(ref=ref, inputs=inputs)
        return {"message": f"Workflow '{workflow_id_or_name}' dispatched successfully on ref '{ref}'!"}
    except (ValueError, GithubException) as e:
        return {"error": f"An unexpected error occurred while triggering workflow: {e}. Ensure workflow_id_or_name is correct and PAT has 'workflow' scope."}


@mcp.tool()
def list_labels(repo_full_name: str, limit: int = 10) -> list[dict]:
    """
    Lists labels for a specified GitHub repository.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        limit (int): Maximum number of labels to return. Defaults to 10.
    Returns:
        list[dict]: A list of dictionaries, each representing a label with 'name', 'color', 'description'.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        labels = repo.get_labels()
        results = []
        for i, label in enumerate(labels):
            if i >= limit: break
            results.append({
                "name": label.name,
                "color": label.color,
                "description": label.description
            })
        return results
    except (ValueError, GithubException) as e:
        return {"error": str(e)}


@mcp.tool()
def create_label(repo_full_name: str, name: str, color: str, description: str = None) -> dict:
    """
    Creates a new label in a specified GitHub repository.
    Args:
        repo_full_name (str): The full name of the repository (e.g., "owner/repo").
        name (str): The name of the label.
        color (str): The color of the label (6-character hexadecimal code, e.g., "f29513").
        description (str, optional): A short description of the label.
    Returns:
        dict: Details of the created label or an error.
    """
    try:
        repo = _get_repo_safe(repo_full_name)
        label = repo.create_label(name=name, color=color, description=description)
        return {
            "message": "Label created successfully!",
            "name": label.name,
            "color": label.color,
            "description": label.description,
            "url": label.url
        }
    except (ValueError, GithubException) as e:
        return {"error": str(e)}


@mcp.tool()
def get_user_profile(username: str) -> dict:
    """
    Gets public profile information for a GitHub user.
    Args:
        username (str): The GitHub username.
    Returns:
        dict: User profile details or an error.
    """
    try:
        user = g.get_user(username)
        return {
            "login": user.login,
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "company": user.company,
            "location": user.location,
            "blog": user.blog,
            "public_repos": user.public_repos,
            "followers": user.followers,
            "following": user.following,
            "created_at": user.created_at.isoformat(),
            "url": user.html_url
        }
    except GithubException as e:
        return {"error": f"Could not retrieve user profile for '{username}'. Error: {e}"}


@mcp.tool()
def list_org_members(org_name: str, limit: int = 10) -> list[dict]:
    """
    Lists members of a GitHub organization.
    Args:
        org_name (str): The name of the GitHub organization.
        limit (int): Maximum number of members to return. Defaults to 10.
    Returns:
        list[dict]: A list of dictionaries, each representing an organization member with 'login', 'id', 'url'.
    """
    try:
        org = g.get_organization(org_name)
        members = org.get_members()
        results = []
        for i, member in enumerate(members):
            if i >= limit: break
            results.append({
                "login": member.login,
                "id": member.id,
                "url": member.html_url
            })
        return results
    except GithubException as e:
        return {"error": f"Could not list organization members for '{org_name}'. Error: {e}"}


@mcp.tool()
def create_gist(public: bool, files: dict, description: str = None) -> dict:
    """
    Creates a new GitHub Gist.
    Args:
        public (bool): True to create a public gist, False for a secret gist.
        files (dict): A dictionary where keys are filenames (e.g., "hello.py") and values are the file content string.
                      Example: {"file1.txt": "Hello World", "file2.js": "console.log('test');"}
        description (str, optional): A description for the gist.
    Returns:
        dict: Details of the created Gist or an error.
    """
    try:
        file_objects = {name: InputFileContent(content) for name, content in files.items()}
        gist = g.create_gist(public=public, files=file_objects, description=description)
        return {
            "message": "Gist created successfully!",
            "id": gist.id,
            "url": gist.html_url,
            "description": gist.description,
            "public": gist.public,
            "files": list(gist.files.keys())
        }
    except GithubException as e:
        return {"error": f"An unexpected error occurred while creating gist: {e}"}


@mcp.tool()
def get_gist_content(gist_id: str) -> dict:
    """
    Retrieves the content of a specific GitHub Gist.
    Args:
        gist_id (str): The ID of the Gist.
    Returns:
        dict: A dictionary where keys are filenames and values are file contents, or an error.
    """
    try:
        gist = g.get_gist(gist_id)
        files_content = {}
        for filename, file_obj in gist.files.items():
            files_content[filename] = file_obj.content
        return {
            "id": gist.id,
            "description": gist.description,
            "public": gist.public,
            "files": files_content
        }
    except GithubException as e:
        return {"error": f"Could not retrieve gist content for ID '{gist_id}'. Error: {e}"}


# --- Run the MCP Server ---
if __name__ == "__main__":
    print("Starting GitHub Manager Full MCP Server...", file=sys.stderr)
    mcp.run()