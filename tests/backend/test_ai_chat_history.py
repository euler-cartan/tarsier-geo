from tarsier.ai import jobs
from tarsier.storage import chats


def test_conversations_are_saved_listed_and_deleted(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    chats.add_exchange("c1", "a", "first question", "first answer")
    chats.add_exchange("c1", "b", "second question", "second answer")
    chats.add_exchange("c1", "a", "follow up", "more")
    assert [c["id"] for c in chats.list_conversations("c1")] == ["a", "b"]
    assert chats.list_conversations("c1")[0]["title"] == "first question"
    assert [m["role"] for m in chats.get_messages("c1", "a")] == ["user", "ai", "user", "ai"]
    assert chats.list_conversations("other") == []
    chats.delete_conversation("c1", "a")
    assert [c["id"] for c in chats.list_conversations("c1")] == ["b"]
    chats.delete_all_for_connection("c1")
    assert chats.list_conversations("c1") == []


def test_a_layer_name_matches_only_as_a_whole_word():
    assert jobs._mentions("changes in demo_values?", "demo_values.csv")
    assert not jobs._mentions("changes in demo_values_old?", "demo_values.csv")
