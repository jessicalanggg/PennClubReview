from app import db


club_tags = db.Table(
    "club_tags",
    db.Column("club_id", db.Integer, db.ForeignKey("club.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tag.id"), primary_key=True),
)

user_favorites = db.Table(
    "user_favorites",
    db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column("club_id", db.Integer, db.ForeignKey("club.id"), primary_key=True),
)


class Club(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False, default="")

    tags = db.relationship(
        "Tag",
        secondary=club_tags,
        back_populates="clubs",
        lazy="selectin",
    )
    favorited_by = db.relationship(
        "User",
        secondary=user_favorites,
        back_populates="favorite_clubs",
        lazy="selectin",
    )

    def to_dict(self):
        return {
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "tags": sorted(tag.name for tag in self.tags),
            "favorite_count": len(self.favorited_by),
        }


class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)

    clubs = db.relationship(
        "Club",
        secondary=club_tags,
        back_populates="tags",
        lazy="selectin",
    )


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)

    # This demonstrates a field we may need internally but should not expose through
    # the public user-profile API.
    email = db.Column(db.String(255), unique=True, nullable=True)

    favorite_clubs = db.relationship(
        "Club",
        secondary=user_favorites,
        back_populates="favorited_by",
        lazy="selectin",
    )

    def to_public_dict(self):
        return {
            "username": self.username,
            "name": self.name,
            "favorites": sorted(club.code for club in self.favorite_clubs),
        }
