import os
import sys
import json
import pathlib
import logging
from tufup.repo import Repository, DEFAULT_EXPIRATION_DAYS, Keys # Import Keys class
from tufup.repo import Roles # Import Roles class

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def manage_tuf_metadata(app_version: str, artifacts_dir: str, keys_dir: str, repo_dir: str):
    logger.info(f"Starting TUF metadata management for version: {app_version}")
    logger.info(f"Artifacts directory: {artifacts_dir}")
    logger.info(f"Keys directory: {keys_dir}")
    logger.info(f"Repository directory: {repo_dir}")

    # Load config from .tufup-repo-config
    config_path = pathlib.Path(os.getcwd()) / '.tufup-repo-config'
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)
    
    # Use Repository.from_config() to initialize the repository
    # This will load keys and roles without trying to create new keys.
    repository = Repository.from_config()

    # Ensure the repository paths are correctly set, as from_config might use cwd
    # This is important because the workflow runs in GITHUB_WORKSPACE, but repo_dir might be relative.
    repository.repo_dir = pathlib.Path(repo_dir).resolve()
    repository.keys_dir = pathlib.Path(keys_dir).resolve()
    
    # Ensure dirs exist (from Repository.initialize)
    for path in [repository.keys_dir, repository.metadata_dir, repository.targets_dir]:
        path.mkdir(parents=True, exist_ok=True)

    # Add all artifact bundles for the current version
    for root, _, files in os.walk(artifacts_dir):
        for artifact_file in files:
            # Filter for zip files that start with the app name and current version
            # Account for 'v' prefix in artifact file names
            if artifact_file.startswith(f"{repository.app_name}-v{app_version}") and artifact_file.endswith(".zip"):
                bundle_path = pathlib.Path(root) / artifact_file
                logger.info(f"Adding bundle: {bundle_path}")
                repository.add_bundle(
                    new_bundle_dir=bundle_path,
                    new_version=app_version,
                    skip_patch=False, # We want patches
                    custom_metadata=None,
                    required=False
                )
                logger.info(f"Bundle added: {bundle_path}")

    # Publish changes (sign and save metadata)
    # This will sign targets, snapshot, and timestamp.
    logger.info("Publishing changes (signing metadata)...")
    repository.publish_changes(private_key_dirs=[pathlib.Path(keys_dir)])
    logger.info("Metadata published successfully.")

if __name__ == "__main__":
    if len(sys.argv) != 5:
        logger.error("Usage: python tuf_manager.py <app_version> <artifacts_dir> <keys_dir> <repo_dir>")
        sys.exit(1)

    app_version = sys.argv[1]
    artifacts_dir = sys.argv[2]
    keys_dir = sys.argv[3]
    repo_dir = sys.argv[4]

    manage_tuf_metadata(app_version, artifacts_dir, keys_dir, repo_dir)