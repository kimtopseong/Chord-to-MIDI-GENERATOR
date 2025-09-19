import os
import sys
import json
import pathlib
import shutil
import tarfile
from datetime import datetime, timedelta
import logging
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

try:
    from tuf.api.metadata import (
        Root, Snapshot, Targets, Timestamp, Metadata, TargetFile, MetaFile
    )
    from tuf.api.serialization.json import JSONSerializer
    from securesystemslib.signer import SSlibSigner
    from securesystemslib.interface import (
        import_ed25519_privatekey_from_file,
    )
except ImportError as e:
    logging.error(f"Failed to import TUF/securesystemslib modules: {e}")
    sys.exit(1)

# 1. Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def main():
    # 2. Get base paths
    try:
        app_version = sys.argv[1]
        artifacts_dir_name = sys.argv[2]
        keys_dir_name = sys.argv[3]
        repo_dir_name = sys.argv[4]
        app_name = "Chord-to-MIDI-GENERATOR"

        cwd = pathlib.Path.cwd()
        logger.info(f"Current Working Directory: {cwd}")

        artifacts_dir = cwd / artifacts_dir_name
        keys_dir = cwd / keys_dir_name
        repo_dir = cwd / repo_dir_name
        metadata_dir = repo_dir / "metadata"
        targets_dir = repo_dir / "targets"

        if not artifacts_dir.is_dir():
            logger.error(f"Artifacts directory not found: {artifacts_dir}")
            sys.exit(1)
        if not keys_dir.is_dir():
            logger.error(f"Keys directory not found: {keys_dir}")
            sys.exit(1)

        metadata_dir.mkdir(parents=True, exist_ok=True)
        targets_dir.mkdir(parents=True, exist_ok=True)

    except IndexError:
        logger.error(
            "Usage: python tuf_manager.py <app_version> <artifacts_dir> <keys_dir> <repo_dir>"
        )
        sys.exit(1)
    except Exception as e:
        logger.error(f"An error occurred during setup: {e}")
        sys.exit(1)

    # 3. Load or create metadata
    logger.info("Loading or creating metadata...")
    
    # Root
    root_path = metadata_dir / "root.json"
    if not root_path.exists():
        logger.error(f"Initial root.json not found at {root_path}")
        sys.exit(1)
    root_meta = Metadata.from_file(str(root_path))
    root = root_meta.signed
    root.version += 1
    root.expires = datetime.utcnow().replace(microsecond=0) + timedelta(days=365)
    logger.info(f"Root version bumped to {root.version}")

    # Targets
    targets_path = metadata_dir / "targets.json"
    targets_meta = Metadata.from_file(str(targets_path)) if targets_path.exists() else Metadata(Targets())
    targets = targets_meta.signed
    targets.version += 1
    targets.expires = datetime.utcnow().replace(microsecond=0) + timedelta(days=7)

    # Snapshot
    snapshot_path = metadata_dir / "snapshot.json"
    snapshot_meta = Metadata.from_file(str(snapshot_path)) if snapshot_path.exists() else Metadata(Snapshot())
    snapshot = snapshot_meta.signed
    snapshot.version += 1
    snapshot.expires = datetime.utcnow().replace(microsecond=0) + timedelta(days=7)

    # Timestamp
    timestamp = Timestamp()
    timestamp.version += 1
    timestamp.expires = datetime.utcnow().replace(microsecond=0) + timedelta(days=1)

    # 4. Create archive and update targets
    logger.info("Creating and adding archive to targets...")
    archive_filename = f"{app_name}-{app_version}.tar.gz"
    archive_path = targets_dir / archive_filename
    
    with tarfile.open(archive_path, "w:gz") as tar:
        for item in artifacts_dir.glob("**/*.zip"):
            tar.add(item, arcname=item.name)
            logger.info(f"  - Added {item.name} to archive.")

    if not archive_path.exists():
        logger.error(f"FATAL: Archive file was not created at '{archive_path}'")
        sys.exit(1)
    
    os.chdir(targets_dir)
    target_file = TargetFile.from_file(archive_filename, archive_filename)
    targets.targets[archive_filename] = target_file
    logger.info(f"Added '{archive_filename}' to targets.")

    # 5. Update meta fields in snapshot and timestamp
    snapshot.meta["targets.json"] = MetaFile(version=targets.version)
    timestamp.snapshot_meta = MetaFile(version=snapshot.version)

    # 6. Sign all metadata
    logger.info("Signing all metadata...")
    serializer = JSONSerializer(compact=False)
    
    for role_name, meta_obj in [
        ("root", root_meta),
        ("targets", targets_meta),
        ("snapshot", snapshot_meta),
        ("timestamp", Metadata(timestamp)),
    ]:
        key_path = keys_dir / role_name
        private_key = import_ed25519_privatekey_from_file(str(key_path))
        signer = SSlibSigner(private_key)
        
        # Clear old signatures and sign
        meta_obj.signatures.clear()
        meta_obj.sign(signer, append=True)
        
        # Write to file
        path = metadata_dir / f"{role_name}.json"
        meta_obj.to_file(str(path), serializer)
        logger.info(f"  - Signed and wrote {path}")

    # 7. Create versioned root.json
    versioned_root_path = metadata_dir / f"{root.version}.root.json"
    shutil.copy(root_path, versioned_root_path)
    logger.info(f"Created versioned root: {versioned_root_path}")

    logger.info("TUF metadata update complete.")

if __name__ == "__main__":
    main()