from neo4j import GraphDatabase
import os


class GraphService:
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI")
        self.user = os.getenv("NEO4J_USER")
        self.password = os.getenv("NEO4J_PASSWORD")

        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password)
        )

    def close(self):
        self.driver.close()

    def test_connection(self):
        with self.driver.session() as session:
            result = session.run(
                "RETURN 'Neo4j connection successful' AS message"
            )
            return result.single()["message"]

    def get_statute_context(self, query: str):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (s:Statute)
                WHERE toLower(s.title) CONTAINS toLower($q)
                   OR toLower(s.section) CONTAINS toLower($q)
                RETURN s.code AS code, s.section AS section, s.title AS title
                LIMIT 5
                """,
                q=query
            )

            return [
                f"{r['code']} Section {r['section']}: {r['title']}"
                for r in result
            ]
