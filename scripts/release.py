import argparse
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "version.json"
PACKAGE_FILE = REPO_ROOT / "package.json"
PACKAGE_LOCK_FILE = REPO_ROOT / "package-lock.json"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_package_lock(version):
    if not PACKAGE_LOCK_FILE.exists():
        return
    payload = load_json(PACKAGE_LOCK_FILE)
    if isinstance(payload, dict):
        payload["version"] = version
        packages = payload.get("packages")
        if isinstance(packages, dict):
            root_pkg = packages.get("")
            if isinstance(root_pkg, dict):
                root_pkg["version"] = version
    write_json(PACKAGE_LOCK_FILE, payload)


def main():
    parser = argparse.ArgumentParser(description="Prepare a new release version.")
    parser.add_argument("version", help="Semver version, for example 1.2.2")
    parser.add_argument("--dry-run", action="store_true", help="Print what would change without writing files.")
    args = parser.parse_args()

    version = str(args.version or "").strip()
    if not SEMVER_RE.match(version):
        raise SystemExit("版本号格式不合法，请使用 x.y.z，例如 1.2.2")

    changes = {
        str(VERSION_FILE.relative_to(REPO_ROOT)): {"version": version},
        str(PACKAGE_FILE.relative_to(REPO_ROOT)): None,
        str(PACKAGE_LOCK_FILE.relative_to(REPO_ROOT)): None if PACKAGE_LOCK_FILE.exists() else "missing",
    }

    package_json = load_json(PACKAGE_FILE)
    package_json["version"] = version
    changes[str(PACKAGE_FILE.relative_to(REPO_ROOT))] = {"version": version}

    package_lock_json = None
    if PACKAGE_LOCK_FILE.exists():
        package_lock_json = load_json(PACKAGE_LOCK_FILE)
        changes[str(PACKAGE_LOCK_FILE.relative_to(REPO_ROOT))] = {"version": version}

    if args.dry_run:
        print(json.dumps({"version": version, "changes": changes}, ensure_ascii=False, indent=2))
        return

    write_json(VERSION_FILE, {"version": version})
    write_json(PACKAGE_FILE, package_json)
    if package_lock_json is not None:
        update_package_lock(version)

    print(f"已更新版本到 {version}")
    print("下一步建议：")
    print("1. git diff")
    print(f'2. git commit -am "release: v{version}"')
    print(f"3. git tag v{version}")
    print("4. git push origin main --tags")
    print("5. git push gitee main --tags")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消。")
        raise SystemExit(1)
    except Exception as err:
        print(f"错误: {err}", file=sys.stderr)
        raise SystemExit(1)
