from pathlib import Path
import logging
import os
import subprocess
import tempfile
import re
import shutil


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("__main__")

def _save_source_to_repo(task_id: str, filename: str, source_code: str) -> None:
    """Push the source file directly to the remote repository's main branch.
    Uses a temporary git repo to commit and push the provided file. The
    function is best-effort and logs failures instead of raising.
    """

    artifacts_remote = os.environ.get('CODE_ARTIFACTS')
    auto_push = str(os.environ.get('ARTIFACTS_AUTO_PUSH', '')).lower() in ('1', 'true', 'yes')
    if not auto_push:
        logger.info("ARTIFACTS_AUTO_PUSH not enabled; skipping push of successful source to remote.")
        return
    if not artifacts_remote:
        logger.info("CODE_ARTIFACTS not set; skipping push of successful source to remote.")
        return

    if shutil.which('git') is None:
        logger.warning("'git' not found in PATH; skipping push of successful source to remote. Install Git or add it to PATH to enable auto-push.")
        return

    def _mask_remote(url: str) -> str:
        return re.sub(r'://[^@]+@', '://****@', url)

    def _run_git(args, cwd):
        return subprocess.run(args, cwd=str(cwd), check=False, capture_output=True)

    def _init_repo(cwd):
        # initialize repo and set user config
        res = _run_git(["git", "init"], cwd)
        if res.returncode != 0:
            logger.warning(f"git init failed: {res.stderr.decode('utf-8', errors='ignore') or res.stdout.decode('utf-8', errors='ignore')}")
            return False
        # set minimal user config
        _run_git(["git", "config", "user.email", "actions@localhost"], cwd)
        _run_git(["git", "config", "user.name", "Impactra Bot"], cwd)
        return True

    def _write_and_commit(task_dir, target_path, msg):
        try:
            _run_git(["git", "add", str(target_path)], task_dir)
            c = _run_git(["git", "commit", "-m", msg], task_dir)
            return c
        except Exception as e:
            logger.warning(f"Commit failed: {e}")
            return None

    def _ensure_remote(td_path, remote_url):
        r = _run_git(["git", "remote", "add", "origin", remote_url], td_path)
        if r.returncode != 0:
            # try set-url if remote exists
            _run_git(["git", "remote", "set-url", "origin", remote_url], td_path)

    try:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            # write the file at repo root (no parent task_ folder)
            target = td_path / filename
            with open(target, 'w', encoding='utf-8') as f:
                f.write(source_code)

            if not _init_repo(td_path):
                return

            commit_msg = f"Add successful source for task {task_id}: {filename}"
            _write_and_commit(td_path, target, commit_msg)

            _ensure_remote(td_path, artifacts_remote)

            # initial push
            push = _run_git(["git", "push", "origin", "HEAD:refs/heads/main"], td_path)
            if push.returncode == 0:
                logger.info(f"Successfully pushed source for task {task_id} to remote { _mask_remote(artifacts_remote) } on branch main")
                return

            stderr = push.stderr.decode('utf-8', errors='ignore')
            logger.warning(f"Initial push to remote { _mask_remote(artifacts_remote) } failed: {stderr}")

            # If remote rejects due to non-fast-forward, attempt safe recovery
            rejected_indicators = ('non-fast-forward', 'fetch first', 'rejected', 'Updates were rejected')
            if any(ind in stderr for ind in rejected_indicators):
                logger.info("Initial push was rejected due to remote changes; attempting a safe force-with-lease push to main")
                force_push = _run_git(["git", "push", "--force-with-lease", "origin", "HEAD:refs/heads/main"], td_path)
                if force_push.returncode == 0:
                    logger.info(f"Force-pushed source for task {task_id} to remote { _mask_remote(artifacts_remote) } on branch main")
                    return

                fstderr = force_push.stderr.decode('utf-8', errors='ignore')
                logger.warning(f"Force push failed: {fstderr}")

                # If force fails (stale info or fetch required), fetch and merge to preserve remote content
                if 'stale' in fstderr.lower() or 'stale info' in fstderr.lower() or 'fetch first' in stderr.lower():
                    logger.info("Initial push rejected; attempting to fetch and merge remote changes before pushing to avoid overwriting existing files")

                    fetch = _run_git(["git", "fetch", "origin", "main"], td_path)
                    if fetch.returncode != 0:
                        fmsg = fetch.stderr.decode('utf-8', errors='ignore') or fetch.stdout.decode('utf-8', errors='ignore')
                        logger.warning(f"Failed to fetch origin/main: {fmsg}")
                    else:
                        # Try normal merge first
                        merge = _run_git(["git", "merge", "--no-edit", "origin/main"], td_path)
                        if merge.returncode == 0:
                            logger.info("Merged origin/main into local commit successfully")
                            push2 = _run_git(["git", "push", "origin", "HEAD:refs/heads/main"], td_path)
                            if push2.returncode == 0:
                                logger.info(f"Pushed source for task {task_id} to remote { _mask_remote(artifacts_remote) } on branch main after merge")
                                return
                            else:
                                pmsg = push2.stderr.decode('utf-8', errors='ignore') or push2.stdout.decode('utf-8', errors='ignore')
                                logger.warning(f"Push after merge failed: {pmsg}")
                        else:
                            mmsg = merge.stderr.decode('utf-8', errors='ignore') or merge.stdout.decode('utf-8', errors='ignore')
                            logger.warning(f"Merge failed: {mmsg}")

                            # If unrelated histories, retry merge allowing unrelated histories
                            if 'refusing to merge unrelated histories' in mmsg.lower() or 'unrelated histories' in mmsg.lower():
                                logger.info("Remote and local histories appear unrelated; retrying merge with --allow-unrelated-histories")
                                merge2 = _run_git(["git", "merge", "--allow-unrelated-histories", "--no-edit", "origin/main"], td_path)
                                if merge2.returncode == 0:
                                    logger.info("Merge with --allow-unrelated-histories succeeded")
                                    push3 = _run_git(["git", "push", "origin", "HEAD:refs/heads/main"], td_path)
                                    if push3.returncode == 0:
                                        logger.info(f"Pushed source for task {task_id} to remote { _mask_remote(artifacts_remote) } on branch main after merge (allow-unrelated-histories)")
                                        return
                                    else:
                                        p3msg = push3.stderr.decode('utf-8', errors='ignore') or push3.stdout.decode('utf-8', errors='ignore')
                                        logger.warning(f"Push after merge (allow-unrelated-histories) failed: {p3msg}")
                                else:
                                    m2msg = merge2.stderr.decode('utf-8', errors='ignore') or merge2.stdout.decode('utf-8', errors='ignore')
                                    logger.warning(f"Merge (allow-unrelated-histories) failed: {m2msg}")

                            # If merge had conflicts, attempt a merge favoring remote changes for conflicts
                            if 'conflict' in mmsg.lower() or 'conflicts' in mmsg.lower():
                                logger.info("Merge had conflicts; attempting merge favoring remote changes (theirs) for conflicted paths")
                                merge3 = _run_git(["git", "merge", "-X", "theirs", "--no-edit", "origin/main"], td_path)
                                if merge3.returncode == 0:
                                    logger.info("Merged with -X theirs successfully")
                                    push4 = _run_git(["git", "push", "origin", "HEAD:refs/heads/main"], td_path)
                                    if push4.returncode == 0:
                                        logger.info(f"Pushed source for task {task_id} to remote { _mask_remote(artifacts_remote) } on branch main after resolving conflicts by favoring remote")
                                        return
                                    else:
                                        p4msg = push4.stderr.decode('utf-8', errors='ignore') or push4.stdout.decode('utf-8', errors='ignore')
                                        logger.warning(f"Push after merge (theirs) failed: {p4msg}")

            # If we reach here, no recovery succeeded
            logger.warning(f"Unable to push source for task {task_id} to remote { _mask_remote(artifacts_remote) } (see previous logs for details)")

    except Exception as e:
        logger.warning(f"Unexpected error while pushing source to remote: {e}")
