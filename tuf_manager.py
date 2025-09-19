import os
import sys
import json
import pathlib
import shutil
import tarfile
from datetime import datetime, timedelta

from tuf.api.metadata import (
    Root, Snapshot, Targets, Timestamp, Metadata, TargetFile
)
from tuf.api.serialization.json import JSONSerializer
from securesystemslib.signer import SSlibSigner
from securesystemslib.interface import (
    import_ed25519_privatekey_from_file,
)

# Configure logging
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TufRepoManager:
    def __init__(self, repo_dir: str, keys_dir: str, app_name: str):
        self.repo_dir = pathlib.Path(repo_dir)
        self.keys_dir = pathlib.Path(keys_dir)
        self.app_name = app_name
        self.metadata_dir = self.repo_dir / 'metadata'
        self.targets_dir = self.repo_dir / 'targets'
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.targets_dir.mkdir(parents=True, exist_ok=True)

    def _load_metadata(self) -> dict[str, Metadata]:
        meta = {}
        for role in ["root", "targets", "snapshot", "timestamp"]:
            path = self.metadata_dir / f"{role}.json"
            if path.exists():
                meta[role] = Metadata.from_file(str(path))
        return meta

    def _sign_metadata(self, role_name: str, metadata: Metadata):
        key_path = self.keys_dir / role_name
        if not key_path.exists():
            raise FileNotFoundError(f"Key file not found: {key_path}")
        
        private_key = import_ed25519_privatekey_from_file(str(key_path))
        signer = SSlibSigner(private_key)
        metadata.sign(signer, append=True)

    def run(self, app_version: str, artifacts_dir: str):
        logger.info("Loading existing metadata...")
        meta = self._load_metadata()

        if "root" not in meta:
            logger.error("root.json not found. Cannot proceed.")
            sys.exit(1)

        # 1. Update root metadata if needed (e.g., refresh expiration)
        root = meta["root"].signed
        root.expires = datetime.utcnow().replace(microsecond=0) + timedelta(days=365)
        root.version += 1
        logger.info(f"Root version bumped to {root.version}")

        # 2. Create a combined archive and add it to targets
        targets = meta.get("targets", Metadata(Targets(expires=datetime.utcnow() + timedelta(days=7)))).signed
        targets.expires = datetime.utcnow().replace(microsecond=0) + timedelta(days=7)
        
        archive_filename = f"{self.app_name}-{app_version}.tar.gz"
        archive_path = self.targets_dir / archive_filename
        
        with tarfile.open(archive_path, "w:gz") as tar:
            for root_dir, _, files in os.walk(artifacts_dir):
                for file in files:
                    if file.endswith(".zip"):
                        full_path = pathlib.Path(root_dir) / file
                        tar.add(full_path, arcname=file)
                        logger.info(f"Added to archive: {file}")

        target_file = TargetFile.from_file(os.path.abspath(archive_path), str(archive_path.relative_to(self.repo_dir)))
        targets.targets[archive_filename] = target_file
        logger.info(f"Added to targets: {archive_filename}")

        # 3. Update snapshot
        snapshot = meta.get("snapshot", Metadata(Snapshot(expires=datetime.utcnow() + timedelta(days=7)))).signed
        snapshot.expires = datetime.utcnow().replace(microsecond=0) + timedelta(days=7)
        snapshot.meta["targets.json"] = MetaFile(version=targets.version)

        # 4. Update timestamp
        timestamp = meta.get("timestamp", Metadata(Timestamp(expires=datetime.utcnow() + timedelta(days=1)))).signed
        timestamp.expires = datetime.utcnow().replace(microsecond=0) + timedelta(days=1)
        timestamp.snapshot_meta = MetaFile(version=snapshot.version)

        # 5. Sign and write all metadata
        for role_name, metadata_obj in [("root", meta["root"]), ("targets", Metadata(targets)), ("snapshot", Metadata(snapshot)), ("timestamp", Metadata(timestamp))]:
            metadata_obj.signatures.clear()
            self._sign_metadata(role_name, metadata_obj)
            metadata_obj.to_file(str(self.metadata_dir / f"{role_name}.json"), JSONSerializer(compact=False))
            logger.info(f"Signed and wrote {role_name}.json")

        # Create versioned root.json
        versioned_root_path = self.metadata_dir / f"{root.version}.root.json"
        shutil.copy(self.metadata_dir / "root.json", versioned_root_path)
        logger.info(f"Created versioned root metadata: {versioned_root_path}")

if __name__ == "__main__":
    if len(sys.argv) != 5:
        logger.error("Usage: python tuf_manager.py <app_version> <artifacts_dir> <keys_dir> <repo_dir>")
        sys.exit(1)

    app_version = sys.argv[1]
    artifacts_dir = sys.argv[2]
    keys_dir = sys.argv[3]
    repo_dir = sys.argv[4]

    manager = TufRepoManager(repo_dir, keys_dir, "Chord-to-MIDI-GENERATOR")
    manager.run(app_version, artifacts_dir)
