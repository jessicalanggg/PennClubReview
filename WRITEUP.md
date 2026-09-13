# Open-Ended Questions

## 1. Authentication

For a production version of Penn Club Review, I would avoid creating a custom authentication protocol. If Penn provides an institutional identity provider, I would prefer OAuth 2.0/OpenID Connect (OIDC) so users can authenticate through Penn without the application managing passwords directly.

If the application manages its own accounts, I would create:

- `POST /api/auth/signup` — validate input and create a user.
- `POST /api/auth/login` — verify credentials and create a session.
- `POST /api/auth/logout` — invalidate the session.
- `GET /api/auth/me` — return the currently authenticated user.

The `User` table would store a `password_hash`, never a plaintext password. Passwords should be hashed with Argon2id or bcrypt, using a unique salt. In Python, I would use packages such as `argon2-cffi`, `bcrypt`, or Werkzeug's password utilities. This limits the damage if an attacker gains access to the database because they cannot directly retrieve users' passwords.

I would also protect the system by rate-limiting login attempts with `Flask-Limiter`, validating all request data, using generic login errors to prevent username enumeration, storing application secrets in environment variables, and using HTTPS with secure session cookies. SQLAlchemy's parameterized queries would help prevent SQL injection.

Authentication should also be separated from authorization. Logging in proves who a user is, while authorization determines what they can do—for example, only a club administrator should be allowed to edit a club.

For Penn-based authentication, I would use OIDC's authorization-code flow, potentially implemented with Python's `Authlib`, rather than designing a custom authentication or token system.

The most important design principle is that a database compromise should not automatically expose reusable user passwords, and possession of an authenticated session should still not grant access to actions the user is not authorized to perform.

---

## 2. Club Comments

I would use a single `Comment` table for both top-level comments and replies. A reply is still a comment; it simply stores the `id` of another comment as its parent. This creates a self-referential one-to-many relationship and supports reply chains of any depth.

```python
class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    club_id = db.Column(
        db.Integer,
        db.ForeignKey("club.id"),
        nullable=False,
    )

    parent_id = db.Column(
        db.Integer,
        db.ForeignKey("comment.id"),
        nullable=True,
    )
```

The relationships would be:

```text
User 1 -------- * Comment
Club 1 -------- * Comment
Comment 1 ----- * Comment
        parent     replies
```

A top-level comment would have `parent_id = None`:

```python
comment = Comment(
    body="Great workshops!",
    user_id=current_user.id,
    club_id=club.id,
    parent_id=None,
)
```

A reply would use the same model but reference its parent:

```python
reply = Comment(
    body="Are beginners welcome?",
    user_id=current_user.id,
    club_id=club.id,
    parent_id=parent_comment.id,
)
```

In SQLAlchemy, I would define the self-referencing relationship with `parent` and `replies`:

```python
parent = db.relationship(
    "Comment",
    remote_side=[id],
    back_populates="replies",
)

replies = db.relationship(
    "Comment",
    back_populates="parent",
)
```

This is preferable to separate tables for comments and replies because one schema naturally supports unlimited reply depth while keeping the database structure simple.

## 3. Route Caching

I would cache read-heavy GET routes that are requested frequently and require more work than a simple lookup. Good candidates are:

- `GET /api/clubs` — likely high traffic and may include computed values such as favorite counts.
- `GET /api/tags` — may require `COUNT`/`GROUP BY` aggregation.
- `GET /api/clubs/search?q=...` — repeated searches can be cached using the normalized query string.

I would avoid caching `POST`, `PATCH`, and `DELETE` responses because they modify application state.

For Flask, I would use Flask-Caching. In production, I would back it with Redis so multiple application instances share the same cache. A simple process-local cache is acceptable for development but not ideal once the application is scaled.

Example cache keys could be:

```text
clubs:list:v1
tags:counts:v1
clubs:search:v1:penn
```

Search terms should be normalized, for example by trimming whitespace and converting to lowercase.

The main challenge is cache invalidation. I would invalidate related cache entries whenever data changes. For example:

```text
POST/PATCH club      -> invalidate club list and search caches
club tag changes     -> invalidate tag counts
favorite changes     -> invalidate club list if favorite_count is included
```

For search results, instead of deleting every possible search key, I could use a version number:

```text
clubs:search:v42:penn
```

When club data changes, increment the version to `v43`. New requests use the new version while old entries expire naturally.

I would also use a reasonable TTL as a backup. Shorter TTLs give fresher data, while longer TTLs reduce database load. In production, I would monitor cache hit rate and query latency before caching additional endpoints.