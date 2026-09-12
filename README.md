# Penn Labs Backend Challenge — Penn Club Review

## Overview

This project implements a small Flask REST API backed by SQLite through Flask-SQLAlchemy. The legacy `clubs.json` fixture is normalized into relational models and loaded by `bootstrap.py`.

## Data model

### Club

- `id`: internal integer primary key
- `code`: unique, public/stable club identifier
- `name`: club name
- `description`: club description
- `tags`: many-to-many relationship with `Tag`
- `favorited_by`: many-to-many relationship with `User`

### Tag

Tags are represented as their own model instead of storing the JSON list directly. A club can have many tags and the same tag can belong to many clubs, so a many-to-many relationship avoids duplicated tag strings and makes the tag-count endpoint a direct SQL aggregation.

### User

- `id`: internal integer primary key
- `username`: unique public identifier
- `name`: display name
- `email`: private account field; intentionally omitted from the public profile serializer
- `favorite_clubs`: many-to-many relationship with `Club`

The bootstrap creates `Josh` with username `josh`. The email field demonstrates the distinction between internal account data and fields safe for a public user-profile API. Rather than serializing a model automatically, `User.to_public_dict()` explicitly allow-lists fields that may leave the server.

### Favorites

Favorites use a join table (`user_favorites`) rather than storing a mutable integer on `Club`. This preserves *who* favorited each club and lets the API derive a correct `favorite_count`. The compound primary key also prevents duplicate `(user, club)` favorite rows.

## Installation

1. Install `pipx` if necessary.
2. Install Poetry:

   ```bash
   pipx install poetry
   ```

3. Install dependencies:

   ```bash
   poetry install --no-root
   ```

4. Create and populate the SQLite database:

   ```bash
   poetry run python bootstrap.py
   ```

5. Run the Flask application:

   ```bash
   poetry run flask --app app run --debug
   ```

6. The API is available at `http://127.0.0.1:5000`.

## API

### Get all clubs

`GET /api/clubs`

Returns all clubs as a JSON array. Each club contains its `code`, `name`, `description`, tags, and current `favorite_count`.

### Get a public user profile

`GET /api/users/<username>`

Example:

```text
GET /api/users/josh
```

Returns only public profile information. Private fields such as email are deliberately not serialized.

### Search clubs

`GET /api/clubs/search?q=<substring>`

Example:

```text
GET /api/clubs/search?q=penn
```

The query is case-insensitive and the filtering occurs in SQL using `ILIKE`, rather than loading all clubs into Python. Because this requirement is arbitrary substring matching (`%query%`), a normal B-tree index cannot fully optimize every search. For a much larger production dataset I would consider PostgreSQL trigram indexes or an appropriate full-text/search service.

### Add a club

`POST /api/clubs`

Example body:

```json
{
  "code": "robotics",
  "name": "Penn Robotics Club",
  "description": "A student robotics organization.",
  "tags": ["Technology", "Undergraduate"]
}
```

Returns `201 Created`. Duplicate club codes return `409 Conflict`.

### Favorite or unfavorite a club

Favorite:

```text
POST /api/users/josh/favorites/locustlabs
```

Unfavorite (provided as a symmetric convenience route):

```text
DELETE /api/users/josh/favorites/locustlabs
```

Favorite creation is idempotent: favoriting the same club twice does not create duplicate rows or inflate the count.

### Modify a club

`PATCH /api/clubs/<club_code>`

Example:

```json
{
  "description": "Updated description",
  "tags": ["Technology", "Graduate"]
}
```

Only `name`, `description`, and `tags` can be modified. The stable `code`, internal database ID, and derived `favorite_count` cannot be changed through this endpoint. Unknown/disallowed fields are rejected rather than silently ignored.

### Get club counts by tag

`GET /api/tags`

Example response:

```json
[
  {"tag": "Academic", "club_count": 1},
  {"tag": "Undergraduate", "club_count": 4}
]
```

The count is performed in SQL with `GROUP BY` instead of counting in Python.

## Validation and status codes

- `200 OK` — successful reads, updates, favorites/unfavorites
- `201 Created` — club successfully created
- `400 Bad Request` — invalid JSON, missing/invalid fields, forbidden modifications, missing search query
- `404 Not Found` — requested user or club does not exist
- `409 Conflict` — duplicate club code

## Design decisions

### Why separate `Tag` objects?

The source JSON contains nested tag arrays, but relationally a tag is shared by many clubs. Normalizing tags provides data consistency, supports efficient aggregation, and models the domain relationship directly.

### Why use `code` in URLs?

The supplied data already provides a unique, human-readable code. Internal integer IDs remain implementation details, while the code is a stable API-facing identifier.

### Why `PATCH` for modification?

The challenge says to modify "some" club information. `PATCH` expresses partial updates naturally: clients only send the fields they want changed. A full `PUT` would normally imply replacement of the complete resource.

### Why is `favorite_count` derived?

A stored counter can become inconsistent with the actual favorites unless every write is carefully synchronized. In this challenge, deriving the count from the relationship favors correctness and simplicity. At high scale, a cached/denormalized counter could be introduced with transactional safeguards.

### Privacy

The user-profile endpoint uses an explicit allow-list serializer. This is safer than dumping every database column, because adding a new private column later does not automatically make it public.

## Open-ended architecture considerations

Detailed answers to the challenge's authentication, threaded-comment, and route-caching questions are provided in [`WRITEUP.md`](WRITEUP.md). The proposals are intentionally connected to this implementation: authentication separates private account fields from public serializers, comments extend the existing `User`/`Club` relationships with a self-referential `Comment` model, and cache invalidation accounts for the fact that `/api/clubs` includes relationship-derived `favorite_count`.

## Suggested production improvements

For a production service I would additionally add database migrations, automated pytest coverage, pagination, structured logging/observability, API versioning, PostgreSQL, authorization policies, rate limiting, secure authentication/SSO, Redis-backed caching where profiling justifies it, and more specialized indexing/search if the dataset became large.
