import os
import sys
import json
import pathlib
import logging
from tufup.repo import Repository, DEFAULT_EXPIRATION_DAYS

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
    
    with open(config_path, 'r') as f:
        config = json.load(f)

    app_name = config.get('app_name', 'Chord-to-MIDI-GENERATOR')
    expiration_days = config.get('expiration_days', DEFAULT_EXPIRATION_DAYS)
    key_map = config.get('key_map')
    encrypted_keys = config.get('encrypted_keys')
    thresholds = config.get('thresholds')

    repository = Repository(
        app_name=app_name,
        repo_dir=repo_dir,
        keys_dir=keys_dir,
        expiration_days=expiration_days,
        key_map=key_map,
        encrypted_keys=encrypted_keys,
        thresholds=thresholds
    )

    # Initialize the repository (load keys and roles)
    # This will load existing metadata from repo_dir/metadata
    repository.initialize()

    # Add all artifact bundles for the current version
    for artifact_file in os.listdir(artifacts_dir):
        # Filter for zip files that start with the app name and current version
        if artifact_file.startswith(f"{app_name}-{app_version}") and artifact_file.endswith(".zip"):
            bundle_path = pathlib.Path(artifacts_dir) / artifact_file
            logger.info(f"Adding bundle: {bundle_path}")
            # add_bundle will create the tar.gz and add it to targets.json
            # It will also create patches if a previous version exists.
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
