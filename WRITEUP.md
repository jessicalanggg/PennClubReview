# Open-Ended Questions

## 1. Authentication

For a production version of Penn Club Review, I would avoid inventing a custom authentication protocol. If Penn provides an institutional identity provider, my preferred solution would be to integrate with **OAuth 2.0 / OpenID Connect (OIDC)** so users can authenticate through an existing trusted identity system and the application does not need to own password authentication itself.

If the application needed to manage its own accounts, I would add these routes:

- `POST /api/auth/signup` — create an account after validating the username/email and password policy.
- `POST /api/auth/login` — verify credentials and establish an authenticated session.
- `POST /api/auth/logout` — invalidate/clear the current session.
- `GET /api/auth/me` — return the currently authenticated user's public profile.

I would extend the `User` table with a password hash (for example, `password_hash`) but would **never store plaintext passwords**. Passwords should be hashed with a purpose-built adaptive password hashing algorithm such as **Argon2id** or bcrypt, with a unique salt per password. In Python I would consider `argon2-cffi` (preferred for Argon2id), `bcrypt`, or Werkzeug's password utilities. Even if an attacker obtained a copy of the database, they would get password hashes rather than immediately usable plaintext credentials.

For a traditional Flask web application, I would use **Flask-Login** for authenticated session management. Authentication cookies should be configured with `HttpOnly`, `Secure`, and an appropriate `SameSite` setting and should only be transmitted over HTTPS. If cookie-based authentication is used, state-changing operations also need CSRF protection; `Flask-WTF`/`CSRFProtect` is one established Flask option.

Additional protections I would apply include:

- Rate-limit login/signup attempts (for example with `Flask-Limiter`) to slow brute-force and credential-stuffing attacks.
- Return generic authentication failures so the login endpoint does not reveal whether a username exists.
- Require strong random application/session secrets and keep secrets outside source control, normally in environment variables or a secret manager.
- Use SQLAlchemy parameter binding rather than building SQL from untrusted strings.
- Validate all request data on the server.
- Apply **authorization** independently from authentication. Being logged in answers “Who are you?”; authorization answers “Are you allowed to perform this action?” For example, only authorized club administrators should be able to modify a club.
- Use HTTPS everywhere in production and set secure response headers.
- Add account recovery/email verification flows carefully rather than exposing reset tokens or account existence.

If Penn uses OIDC, a library such as **Authlib** could implement the client side of the authorization-code flow. The server would validate the identity-provider response, create or map a local `User`, and then establish the application's own session. Using a mature standard such as OIDC is more robust than designing a home-grown token format or password exchange.

### Example authentication flow

```text
Browser
   |
   | POST /api/auth/login
   v
Flask
   |
   | verify password hash / OIDC identity
   v
Authenticated session
   |
   | Secure + HttpOnly cookie
   v
Subsequent protected API requests
```

The most important design principle is that a database compromise should not automatically expose reusable user passwords, and possession of an authenticated session should still not grant access to actions the user is not authorized to perform.

---

## 2. Club Comments

I would add a single `Comment` model rather than separate tables for comments and replies. Replies are still comments; the only difference is that a reply references another comment as its parent. This produces a **self-referential one-to-many relationship** (an adjacency-list model) that can support arbitrary reply depth.

A simplified table could look like this:

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

The relationships are:

```text
User 1 -------- * Comment
Club 1 -------- * Comment
Comment 1 ----- * Comment
        parent     replies
```

A top-level comment has `parent_id = NULL`:

```python
comment = Comment(
    body="Great workshops!",
    user_id=current_user.id,
    club_id=club.id,
    parent_id=None,
)
```

A reply uses the exact same model but points to its parent:

```python
reply = Comment(
    body="Are beginners welcome?",
    user_id=current_user.id,
    club_id=club.id,
    parent_id=parent_comment.id,
)
```

That allows a conversation such as:

```text
Comment 17 (Josh)
|-- Comment 18 (Alice, parent_id=17)
    |-- Comment 19 (Josh, parent_id=18)
```

This is preferable to creating tables such as `comments`, `comment_replies`, and `reply_replies`, because a self-reference naturally supports any depth without changing the schema.

I would also define SQLAlchemy relationships similar to:

```python
user = db.relationship("User", back_populates="comments")
club = db.relationship("Club", back_populates="comments")
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

When creating a reply, the API must verify that the parent comment belongs to the same club specified by the route. Otherwise a malformed request could create a reply tree that crosses clubs.

Possible routes would be:

- `GET /api/clubs/<club_code>/comments` — return comments for a club.
- `POST /api/clubs/<club_code>/comments` — create a top-level comment.
- `POST /api/comments/<comment_id>/replies` — reply to an existing comment.
- `PATCH /api/comments/<comment_id>` — edit a user's own comment.
- `DELETE /api/comments/<comment_id>` — delete or soft-delete a user's own comment.

For large discussion trees I would avoid returning an unlimited recursive structure in one request. I could return top-level comments with a limited number of replies, paginate them, or provide a separate endpoint to load children.

Deletion also deserves special treatment. Hard-deleting a parent can destroy the context of replies, so a production implementation could use fields such as `is_deleted` and `deleted_at` and render the parent as `[comment deleted]` while preserving its children. Authentication and authorization would ensure users can only edit/delete comments they own (with separate moderation privileges for administrators).

Useful indexes would include `(club_id, created_at)` for fetching a club's discussion efficiently and `parent_id` for retrieving replies.

---

## 3. Route Caching

Caching is most valuable for **read-heavy GET endpoints whose responses are reused by many clients and are more expensive than a simple primary-key lookup**. In the API implemented for this challenge, the strongest candidates are:

- `GET /api/clubs` — likely one of the most frequently requested pages and includes relationship-derived favorite counts.
- `GET /api/tags` — performs an aggregate `COUNT`/`GROUP BY`, so caching can avoid repeated aggregation work.
- `GET /api/clubs/search?q=...` — popular repeated searches can be cached by normalized query string, although I would limit cache cardinality/TTL so arbitrary search terms do not grow the cache without bound.

I would be cautious about caching `GET /api/users/<username>` once profiles contain personalized or private information. If it were cached, keys would need to be correctly scoped and only public data should ever be cached. I would not cache `POST`, `PATCH`, or `DELETE` responses as reusable representations because those methods mutate state.

For Flask, I would consider **Flask-Caching**. A local in-memory cache can be useful during development, but in production I would prefer **Redis** so all application instances share the same cache. This also matters once the service is horizontally scaled; process-local caches would otherwise disagree with one another.

A conceptual read flow is:

```text
Client
  |
  v
Flask route
  |
  +-- cache hit  --> return cached JSON
  |
  +-- cache miss --> SQLAlchemy query
                       |
                       v
                   serialize
                       |
                       v
                 write Redis key
                       |
                       v
                    response
```

### Cache keys

I would use explicit namespaced keys, for example:

```text
clubs:list:v1
clubs:search:v1:penn
tags:counts:v1
```

Normalizing search keys (for example trimming whitespace and lowercasing the query) prevents separate entries for equivalent searches such as `Penn` and `penn`.

### Cache invalidation

The difficult part of caching is invalidation. I would combine **explicit invalidation on writes** with a moderate TTL as a safety net.

For this API, dependencies are important:

```text
POST /api/clubs ----------------------+--> invalidate clubs:list
PATCH /api/clubs/<code> --------------+--> invalidate relevant search keys
                                      +--> invalidate tags:counts when tags change

POST/DELETE favorite -----------------+--> invalidate clubs:list
                                           (because favorite_count is included)
```

A newly created club can also affect search results and tag counts. A renamed club can change which search queries match it. Changing tags can change `/api/tags`. Favoriting does not change the club itself, but it **does change the serialized `/api/clubs` response** because `favorite_count` is part of that representation. That means favorite writes must invalidate the club-list cache as well.

For search caches, a simple challenge-sized implementation could clear the search-key namespace after a club create/update. At higher scale I could maintain dependency/version information or use versioned keys. One practical pattern is to store a version number such as `clubs_version` and incorporate it into search keys; a club mutation increments the version, making old keys unreachable until TTL removes them.

For example:

```text
clubs:search:v42:penn
```

After a mutation:

```text
clubs_version = 43
```

new requests use:

```text
clubs:search:v43:penn
```

This avoids scanning Redis to delete every possible search key synchronously.

### TTL trade-off

A short TTL means fresher results but more database traffic. A long TTL reduces database load but increases the risk of stale data. Explicit invalidation makes it possible to use a useful TTL without depending on TTL alone for correctness.

In production I would also measure cache hit rate and query latency before caching every endpoint. Caching adds operational complexity, so I would apply it where profiling shows meaningful benefit rather than treating it as a default for every route.
