"""Small zero-dependency smoke test using Flask's built-in test client."""

from app import app


def show(label, response):
    print(f"\n{label}: {response.status_code}")
    print(response.get_json())


with app.test_client() as client:
    show("GET clubs", client.get("/api/clubs"))
    show("GET Josh", client.get("/api/users/josh"))
    show("Search PeNn", client.get("/api/clubs/search?q=PeNn"))
    show("Tag counts", client.get("/api/tags"))
    show("Favorite Locust Labs", client.post("/api/users/josh/favorites/locustlabs"))
    show("Favorite Locust Labs again", client.post("/api/users/josh/favorites/locustlabs"))
    show(
        "Add club",
        client.post(
            "/api/clubs",
            json={
                "code": "robotics",
                "name": "Penn Robotics Club",
                "description": "A student robotics organization.",
                "tags": ["Technology", "Undergraduate"],
            },
        ),
    )
    show(
        "Patch club",
        client.patch(
            "/api/clubs/robotics",
            json={"description": "Build and learn robotics."},
        ),
    )
    show("GET clubs after writes", client.get("/api/clubs"))
