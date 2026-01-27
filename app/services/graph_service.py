import os
from neo4j import GraphDatabase

class GraphService:
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI")
        self.user = os.getenv("NEO4J_USER")
        self.password = os.getenv("NEO4J_PASSWORD")

        if not self.uri:
            self.driver = None
            return

        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password)
        )

    def close(self):
        if self.driver:
            self.driver.close()

    def test_connection(self):
        if not self.driver:
            return "Neo4j not configured"

        with self.driver.session() as session:
            result = session.run(
                "RETURN 'Neo4j connection successful' AS message"
            )
            return result.single()["message"]
