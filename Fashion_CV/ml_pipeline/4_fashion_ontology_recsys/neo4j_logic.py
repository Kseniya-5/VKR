from neo4j import GraphDatabase

class Neo4jRecommender:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        # Создаем индексы для ускорения поиска и MERGE
        self._create_indexes()

    def _create_indexes(self):
        with self.driver.session() as session:
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (i:Item) REQUIRE i.id IS UNIQUE")
            session.run("CREATE INDEX IF NOT EXISTS FOR (c:Category) ON (c.name)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (col:Color) ON (col.name)")

    def close(self):
        self.driver.close()

    def upload_data(self, annotations, batch_size=1000):
        """Пакетная загрузка данных"""
        items_list = []
        for img_path, objects in annotations.items():
            for obj_id, attrs in objects.items():
                items_list.append({
                    "id": f"{img_path}#{obj_id}",
                    "image": img_path,
                    "type": attrs.get("item_type") or "unknown",
                    "color": attrs.get("color") or "unknown",
                    "season": attrs.get("season") or "unknown",
                    "style": attrs.get("style") or "unknown"
                })

        # Загружаем частями по batch_size
        for i in range(0, len(items_list), batch_size):
            batch = items_list[i:i + batch_size]
            with self.driver.session() as session:
                session.execute_write(self._batch_create_items, batch)
            print(f"Загружено {min(i + batch_size, len(items_list))} из {len(items_list)}...")

    @staticmethod
    def _batch_create_items(tx, batch):
        query = (
            "UNWIND $batch AS row "
            "MERGE (i:Item {id: row.id}) "
            "SET i.image = row.image, i.type = row.type, i.color = row.color, "
            "    i.season = row.season, i.style = row.style "
            "WITH i, row "
            "MERGE (c:Category {name: row.type}) "
            "MERGE (col:Color {name: row.color}) "
            "MERGE (s:Season {name: row.season}) "
            "MERGE (st:Style {name: row.style}) "
            "MERGE (i)-[:HAS_CATEGORY]->(c) "
            "MERGE (i)-[:HAS_COLOR]->(col) "
            "MERGE (i)-[:HAS_SEASON]->(s) "
            "MERGE (i)-[:HAS_STYLE]->(st)"
        )
        tx.run(query, batch=batch)

    def get_recommendations(self, preds):
        # (Логика рекомендаций остается прежней)
        with self.driver.session() as session:
            query = (
                "MATCH (i:Item) "
                "OPTIONAL MATCH (i)-[:HAS_CATEGORY]->(c) WHERE c.name IN $items "
                "OPTIONAL MATCH (i)-[:HAS_COLOR]->(col) WHERE col.name IN $colors "
                "OPTIONAL MATCH (i)-[:HAS_SEASON]->(s) WHERE s.name IN $seasons "
                "OPTIONAL MATCH (i)-[:HAS_STYLE]->(st) WHERE st.name IN $styles "
                "WITH i, "
                "     (CASE WHEN c IS NOT NULL THEN 3 ELSE 0 END + "
                "      CASE WHEN col IS NOT NULL THEN 2 ELSE 0 END + "
                "      CASE WHEN st IS NOT NULL THEN 2 ELSE 0 END + "
                "      CASE WHEN s IS NOT NULL THEN 1 ELSE 0 END) AS score "
                "WHERE score > 0 "
                "RETURN i.id AS id, i.image AS image, score "
                "ORDER BY score DESC LIMIT 5"
            )
            result = session.run(query, 
                                 items=preds.get("item", []), 
                                 colors=preds.get("color", []), 
                                 seasons=preds.get("season", []), 
                                 styles=preds.get("style", []))
            return [dict(record) for record in result]
