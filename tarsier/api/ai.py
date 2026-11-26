"""AI drawer jobs 2–4 (PRD §7.7, FSD §11.3). Job 1 stays on the Statistics tab."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from tarsier.ai.client import AIError, AINotConfiguredError
from tarsier.ai.jobs import build_automation, explain_changes, explain_quality
from tarsier.storage import chats
from tarsier.storage import connections as storage

router = APIRouter()


class ChatBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    job: str
    message: str = ""
    schema_name: str = Field(default="", alias="schema")
    name: str = ""
    check_id: str = ""
    conversation_id: str = Field(default="", max_length=64)


@router.post("/api/connections/{connection_id}/ai/chat")
def ai_chat(connection_id: str, body: ChatBody):
    if storage.get_connection(connection_id) is None:
        raise HTTPException(status_code=404, detail="No such connection.")
    try:
        if body.job == "explain-changes":
            return explain_changes(connection_id)
        if body.job == "explain-quality":
            if not body.name or not body.check_id:
                raise HTTPException(status_code=400, detail="Pick a quality check to explain.")
            return explain_quality(connection_id, body.schema_name, body.name, body.check_id)
        if body.job == "ask":
            from tarsier.ai.jobs import answer_question
            history = chats.get_messages(connection_id, body.conversation_id) if body.conversation_id else []
            result = answer_question(connection_id, body.message, history)
            if body.conversation_id:
                chats.add_exchange(connection_id, body.conversation_id, body.message.strip(), result["text"])
            return result
        if body.job == "suggest-questions":
            from tarsier.ai.jobs import suggest_questions
            return suggest_questions(connection_id)
        if body.job == "build-automation":
            if not body.message.strip():
                raise HTTPException(status_code=400, detail="Describe the automation you want.")
            return build_automation(body.message)
        if body.job == "draft-rule":
            from tarsier.ai.jobs import draft_rule
            return draft_rule(connection_id, body.schema_name, body.name, body.message)
    except AINotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail="Unknown AI job.")


def _require(connection_id: str) -> None:
    if storage.get_connection(connection_id) is None:
        raise HTTPException(status_code=404, detail="No such connection.")


@router.get("/api/connections/{connection_id}/ai/conversations")
def list_conversations(connection_id: str):
    _require(connection_id)
    return {"conversations": chats.list_conversations(connection_id)}


@router.get("/api/connections/{connection_id}/ai/conversations/{conversation_id}")
def get_conversation(connection_id: str, conversation_id: str):
    _require(connection_id)
    return {"messages": chats.get_messages(connection_id, conversation_id)}


@router.delete("/api/connections/{connection_id}/ai/conversations/{conversation_id}")
def delete_conversation(connection_id: str, conversation_id: str):
    _require(connection_id)
    chats.delete_conversation(connection_id, conversation_id)
    return {"status": "ok"}
