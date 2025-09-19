import os
import sys
import json
import pathlib
import logging
import shutil
import tarfile # Import tarfile
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

    # Create a temporary directory to combine all platform bundles
    combined_bundle_dir = pathlib.Path(artifacts_dir) / f"combined_bundle_{app_version}"
    combined_bundle_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Created combined bundle directory: {combined_bundle_dir}")

    # Copy all platform-specific zip files into the temporary directory
    found_bundles = False
    for root, dirs, files in os.walk(artifacts_dir): # Added 'dirs'
        # Exclude the combined_bundle_dir from traversal
        if combined_bundle_dir.name in dirs:
            dirs.remove(combined_bundle_dir.name) # Modify dirs in-place

        for artifact_file in files:
            if artifact_file.startswith(f"{repository.app_name}-v{app_version}") and artifact_file.endswith(".zip"):
                src_path = pathlib.Path(root) / artifact_file
                dst_path = combined_bundle_dir / artifact_file
                shutil.copy(src_path, dst_path)
                logger.info(f"Copied {src_path} to {dst_path}")
                found_bundles = True
    
    if not found_bundles:
        logger.error(f"No artifact bundles found for version {app_version} in {artifacts_dir}")
        sys.exit(1)

    # Add the combined bundle to the repository
    logger.info(f"Adding combined bundle for version: {app_version}")
    repository.add_bundle(
        new_bundle_dir=combined_bundle_dir, # Pass the combined directory
        new_version=app_version,
        skip_patch=False,
        custom_metadata=None,
        required=False
    )
    logger.info(f"Combined bundle added for version: {app_version}")

    # Publish changes (sign and save metadata)
    logger.info("Publishing changes (signing metadata)...")
    repository.publish_changes(private_key_dirs=[pathlib.Path(keys_dir)])
    logger.info("Metadata published successfully.")

    # Manually create the versioned root.json file
    root_version = repository.roles.root.signed.version
    versioned_root_path = repository.metadata_dir / f"{root_version}.root.json"
    latest_root_path = repository.metadata_dir / "root.json"
    shutil.copy(latest_root_path, versioned_root_path)
    logger.info(f"Created versioned root metadata: {versioned_root_path}")

    # Clean up the temporary combined bundle directory
    shutil.rmtree(combined_bundle_dir)
    logger.info(f"Cleaned up combined bundle directory: {combined_bundle_dir}")

if __name__ == "__main__":
    if len(sys.argv) != 5:
        logger.error("Usage: python tuf_manager.py <app_version> <artifacts_dir> <keys_dir> <repo_dir>")
        sys.exit(1)

    app_version = sys.argv[1]
    artifacts_dir = sys.argv[2]
    keys_dir = sys.argv[3]
    repo_dir = sys.argv[4]

    manage_tuf_metadata(app_version, artifacts_dir, keys_dir, repo_dir)
