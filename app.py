from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from sqlalchemy.orm import selectinload

DB_FILE = "clubreview.db"

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_FILE}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

from models import Club, Tag, User, club_tags


def error_response(message, status_code):
    return jsonify({"error": message}), status_code


def normalize_tags(raw_tags):
    """Validate and normalize a JSON list of tag names."""
    if not isinstance(raw_tags, list):
        return None, "'tags' must be a JSON array of strings."

    normalized = []
    seen = set()
    for tag in raw_tags:
        if not isinstance(tag, str) or not tag.strip():
            return None, "Every tag must be a non-empty string."
        cleaned = tag.strip()
        key = cleaned.casefold()
        if key not in seen:
            normalized.append(cleaned)
            seen.add(key)

    return normalized, None


def get_or_create_tags(tag_names):
    """Return Tag objects, reusing existing tags case-insensitively."""
    tags = []
    for tag_name in tag_names:
        tag = db.session.execute(
            db.select(Tag).where(func.lower(Tag.name) == tag_name.lower())
        ).scalar_one_or_none()
        if tag is None:
            tag = Tag(name=tag_name)
            db.session.add(tag)
        tags.append(tag)
    return tags


@app.route("/")
def main():
    return "Welcome to Penn Club Review!"


@app.route("/api")
def api():
    return jsonify({"message": "Welcome to the Penn Club Review API!"})


@app.get("/api/clubs")
def get_clubs():
    clubs = db.session.execute(
        db.select(Club)
        .options(selectinload(Club.tags), selectinload(Club.favorited_by))
        .order_by(Club.name)
    ).scalars().all()
    return jsonify([club.to_dict() for club in clubs])


@app.get("/api/users/<string:username>")
def get_user_profile(username):
    user = db.session.execute(
        db.select(User)
        .options(selectinload(User.favorite_clubs))
        .where(User.username == username)
    ).scalar_one_or_none()

    if user is None:
        return error_response("User not found.", 404)

    # Use an explicit public serializer so private fields such as email are never
    # accidentally exposed by this endpoint.
    return jsonify(user.to_public_dict())


@app.get("/api/clubs/search")
def search_clubs():
    query = request.args.get("q", "").strip()
    if not query:
        return error_response("Query parameter 'q' is required.", 400)

    # Filter inside SQL rather than loading every club and filtering in Python.
    clubs = db.session.execute(
        db.select(Club)
        .options(selectinload(Club.tags), selectinload(Club.favorited_by))
        .where(Club.name.ilike(f"%{query}%"))
        .order_by(Club.name)
    ).scalars().all()

    return jsonify([club.to_dict() for club in clubs])


@app.post("/api/clubs")
def add_club():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Request body must be a JSON object.", 400)

    required_fields = ("code", "name", "description", "tags")
    missing = [field for field in required_fields if field not in data]
    if missing:
        return error_response(f"Missing required field(s): {', '.join(missing)}.", 400)

    code = data["code"]
    name = data["name"]
    description = data["description"]

    if not isinstance(code, str) or not code.strip():
        return error_response("'code' must be a non-empty string.", 400)
    if not isinstance(name, str) or not name.strip():
        return error_response("'name' must be a non-empty string.", 400)
    if not isinstance(description, str):
        return error_response("'description' must be a string.", 400)

    tag_names, tag_error = normalize_tags(data["tags"])
    if tag_error:
        return error_response(tag_error, 400)

    code = code.strip()
    if db.session.execute(db.select(Club).where(Club.code == code)).scalar_one_or_none():
        return error_response("A club with that code already exists.", 409)

    club = Club(
        code=code,
        name=name.strip(),
        description=description.strip(),
        tags=get_or_create_tags(tag_names),
    )
    db.session.add(club)
    db.session.commit()

    return jsonify(club.to_dict()), 201


@app.route("/api/users/<string:username>/favorites/<string:club_code>", methods=["POST", "DELETE"])
def favorite_club(username, club_code):
    user = db.session.execute(
        db.select(User)
        .options(selectinload(User.favorite_clubs))
        .where(User.username == username)
    ).scalar_one_or_none()
    if user is None:
        return error_response("User not found.", 404)

    club = db.session.execute(
        db.select(Club)
        .options(selectinload(Club.tags), selectinload(Club.favorited_by))
        .where(Club.code == club_code)
    ).scalar_one_or_none()
    if club is None:
        return error_response("Club not found.", 404)

    if request.method == "POST":
        if club not in user.favorite_clubs:
            user.favorite_clubs.append(club)
            db.session.commit()
        return jsonify(club.to_dict())

    if club in user.favorite_clubs:
        user.favorite_clubs.remove(club)
        db.session.commit()
    return jsonify(club.to_dict())


@app.patch("/api/clubs/<string:club_code>")
def modify_club(club_code):
    club = db.session.execute(
        db.select(Club)
        .options(selectinload(Club.tags), selectinload(Club.favorited_by))
        .where(Club.code == club_code)
    ).scalar_one_or_none()
    if club is None:
        return error_response("Club not found.", 404)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Request body must be a JSON object.", 400)
    if not data:
        return error_response("At least one field must be provided.", 400)

    allowed_fields = {"name", "description", "tags"}
    disallowed = set(data) - allowed_fields
    if disallowed:
        return error_response(
            "Field(s) cannot be modified: " + ", ".join(sorted(disallowed)) + ".",
            400,
        )

    if "name" in data:
        if not isinstance(data["name"], str) or not data["name"].strip():
            return error_response("'name' must be a non-empty string.", 400)
        club.name = data["name"].strip()

    if "description" in data:
        if not isinstance(data["description"], str):
            return error_response("'description' must be a string.", 400)
        club.description = data["description"].strip()

    if "tags" in data:
        tag_names, tag_error = normalize_tags(data["tags"])
        if tag_error:
            return error_response(tag_error, 400)
        club.tags = get_or_create_tags(tag_names)

    db.session.commit()
    return jsonify(club.to_dict())


@app.get("/api/tags")
def get_tag_counts():
    rows = db.session.execute(
        db.select(Tag.name, func.count(club_tags.c.club_id).label("club_count"))
        .outerjoin(club_tags, Tag.id == club_tags.c.tag_id)
        .group_by(Tag.id, Tag.name)
        .order_by(Tag.name)
    ).all()

    return jsonify(
        [{"tag": tag_name, "club_count": club_count} for tag_name, club_count in rows]
    )


if __name__ == "__main__":
    app.run()
