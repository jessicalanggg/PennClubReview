import json
import os

from app import app, db, DB_FILE
from models import Club, Tag, User


def create_user():
    """Create the starter user required by the challenge."""
    josh = User(username="josh", name="Josh", email="josh@example.com")
    db.session.add(josh)
    db.session.commit()


def load_data():
    """Load clubs.json and normalize tags into the relational database."""
    json_path = os.path.join(os.path.dirname(__file__), "clubs.json")

    with open(json_path, "r", encoding="utf-8") as file:
        clubs_data = json.load(file)

    tags_by_name = {}

    for club_data in clubs_data:
        club = Club(
            code=club_data["code"],
            name=club_data["name"],
            description=club_data.get("description", ""),
        )

        for tag_name in club_data.get("tags", []):
            tag = tags_by_name.get(tag_name)
            if tag is None:
                tag = Tag(name=tag_name)
                tags_by_name[tag_name] = tag
            club.tags.append(tag)

        db.session.add(club)

    db.session.commit()


# No need to modify the below code.
if __name__ == "__main__":
    # Delete any existing database before bootstrapping a new one.
    LOCAL_DB_FILE = "instance/" + DB_FILE
    if os.path.exists(LOCAL_DB_FILE):
        os.remove(LOCAL_DB_FILE)

    with app.app_context():
        db.create_all()
        create_user()
        load_data()
