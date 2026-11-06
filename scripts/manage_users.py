"""
Manage pilot users. Adding the first user switches the tool from demo mode to pilot mode (logins required for actions).

  python scripts/manage_users.py add <username> "<Full name>" <role>      (asks for the password; at least 10 characters)
  python scripts/manage_users.py remove <username>
  python scripts/manage_users.py list

Roles: traffic, finance, approver, viewer, admin. Passwords are stored only as salted hashes in data/users.json.
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services import auth  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("add", "remove", "list"):
        print(__doc__)
        return 1
    if argv[0] == "list":
        users = auth.load_users()
        print("Demo mode (no users)." if not users else "\n".join(f"{u:15} {v['role']:9} {v['full_name']}" for u, v in users.items()))
        return 0
    if argv[0] == "remove":
        print("removed" if auth.remove_user(argv[1]) else "no such user")
        return 0
    if len(argv) != 4:
        print(__doc__)
        return 1
    pw = getpass.getpass("Password (at least 10 characters): ")
    if pw != getpass.getpass("Again: "):
        print("Passwords do not match.")
        return 1
    auth.add_user(argv[1], argv[2], argv[3], pw)
    print(f"Added {argv[1]} ({argv[3]}). The tool is now in pilot mode.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
