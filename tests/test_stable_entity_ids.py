"""Cross-platform contract tests for deterministic Entity IDs."""

import unittest

from core.models import SourceRef, WorldModel, stable_entity_id, stable_relation_id


class StableEntityIdTests(unittest.TestCase):
    def test_shared_python_typescript_vectors(self) -> None:
        vectors = {
            "A": "ent_6dcd4ce23d88",
            "B": "ent_ae4f281df5a5",
            "Alice": "ent_35318264c9a9",
            "東京": "ent_681ee300008e",
            "主人公": "ent_8f07c23f5f99",
            "Axral": "ent_2e44e0745152",
        }
        for name, expected in vectors.items():
            with self.subTest(name=name):
                self.assertEqual(stable_entity_id(name), expected)

    def test_same_name_is_deterministic(self) -> None:
        self.assertEqual(stable_entity_id("主人公"), stable_entity_id("主人公"))

    def test_relation_ids_are_stable_across_models(self) -> None:
        source = SourceRef(line=1, text="A -> B : 友好")
        first = WorldModel()
        a = first.get_or_create_entity("A", None, source)
        b = first.get_or_create_entity("B", None, source)
        relation_a = first.add_relation(a.id, b.id, "友好", source)

        second = WorldModel()
        a2 = second.get_or_create_entity("A", None, source)
        b2 = second.get_or_create_entity("B", None, source)
        relation_b = second.add_relation(a2.id, b2.id, "友好", source)
        self.assertEqual(relation_a.id, relation_b.id)
        self.assertEqual(relation_a.id, stable_relation_id("A->B#0"))
        duplicate = second.add_relation(a2.id, b2.id, "敵対", SourceRef(line=2, text="A -> B : 敵対"))
        self.assertNotEqual(relation_a.id, duplicate.id)

    def test_names_are_not_normalized_implicitly(self) -> None:
        # Hashing follows exact UTF-8 input bytes; normalization is a separate policy.
        self.assertNotEqual(stable_entity_id("é"), stable_entity_id("e\u0301"))


if __name__ == "__main__":
    unittest.main()
