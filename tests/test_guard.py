import pytest

from waypoint.graph.guard import UnsafeCypherError, check_read_only, is_read_only

ACCEPTED = [
    "RETURN 1",
    "MATCH (e:Employee {id: $id})-[:REPORTS_TO]->(m) RETURN m.name",
    "MATCH (e:Employee) WHERE e.created_at > $d RETURN e.id",  # created_at is not CREATE
    "MATCH (p:Policy) WHERE p.title CONTAINS 'Delete old data' RETURN p.id",
    'MATCH (p:Policy) WHERE p.text = "how to SET up VPN" RETURN p',
    "MATCH (n) RETURN n // CREATE (x)",
    "MATCH (n) /* MERGE (x) \n DELETE n */ RETURN n",
    "MATCH (n:`Call Log`) RETURN n",
    r"MATCH (n) WHERE n.s = 'it\'s CREATE' RETURN n",
    "MATCH (d:Department)<-[:IN]-(e) RETURN d.name, count(e) AS headcount",
    "MATCH (n) RETURN n.reset_date, n.offset",  # reset/offset are not SET
]

REJECTED = [
    ("CREATE (:Tmp)", "CREATE"),
    ("create (:Tmp)", "CREATE"),
    ("MERGE (n:Employee {id: 'x'})", "MERGE"),
    ("MATCH (n) DELETE n", "DELETE"),
    ("MATCH (n) DETACH DELETE n", "DETACH"),
    ("MATCH (n) SET n.x = 1", "SET"),
    ("MATCH (n) REMOVE n:Label", "REMOVE"),
    ("DROP INDEX foo", "DROP"),
    ("LOAD CSV FROM 'file:///x.csv' AS row RETURN row", "LOAD CSV"),
    ("load\n  csv from 'x' AS r RETURN r", "LOAD CSV"),
    ("CALL db.labels()", "CALL"),
    ("MATCH (n) CALL { WITH n RETURN n } RETURN n", "CALL"),
    # index procedures stay rejected: only waypoint.graph.db.run_read_trusted may run them
    ("CALL db.index.vector.queryNodes('chunk_embedding', 5, $v) YIELD node RETURN node", "CALL"),
    ("CALL db.index.fulltext.queryNodes('chunk_text', $q) YIELD node RETURN node", "CALL"),
    ("MATCH (n) RETURN n; CREATE (:Tmp)", "CREATE"),
    ("MATCH (n) WHERE n.s = 'safe' CREATE (:Tmp)", "CREATE"),
]


@pytest.mark.parametrize("cypher", ACCEPTED)
def test_accepts_read_queries(cypher: str) -> None:
    check_read_only(cypher)
    assert is_read_only(cypher)


@pytest.mark.parametrize(("cypher", "keyword"), REJECTED)
def test_rejects_write_keywords(cypher: str, keyword: str) -> None:
    with pytest.raises(UnsafeCypherError, match=keyword):
        check_read_only(cypher)
    assert not is_read_only(cypher)


@pytest.mark.parametrize("cypher", ["MATCH (n) WHERE n.s = 'open RETURN n", "MATCH (n) /* CREATE"])
def test_rejects_unterminated_literals(cypher: str) -> None:
    assert not is_read_only(cypher)
