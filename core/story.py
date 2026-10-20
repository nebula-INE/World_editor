"""Portable Axral Story v1 codec; deliberately separate from world-project persistence."""
from __future__ import annotations
from copy import deepcopy
from typing import Any
import json

STORY_FORMAT = "axral-story"
STORY_SCHEMA_VERSION = 1
WORK_KINDS = {"novel", "screenplay", "audio_drama", "game_scenario", "trpg_scenario", "storyboard"}
BLOCK_TYPES = {"prose", "dialogue", "narration", "direction", "note"}

def _obj(value: Any, path: str) -> dict:
    if not isinstance(value, dict): raise ValueError(f"{path}はオブジェクトである必要があります。")
    return value

def _str(value: Any, path: str) -> str:
    if not isinstance(value, str): raise ValueError(f"{path}は文字列である必要があります。")
    return value

def _order(value: Any, path: str, expected: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != expected:
        raise ValueError(f"{path}は配列位置と一致する整数({expected})である必要があります。")

def parse_story(payload: Any) -> dict[str, Any]:
    """Validate and detach a story document; never invokes the existing project codec."""
    doc = _obj(payload, "story")
    if doc.get("format") != STORY_FORMAT: raise ValueError("Axral Story形式ではありません。")
    version = doc.get("schema_version")
    # bool is a subclass of int in Python, so True must not be accepted as version 1.
    if isinstance(version, bool) or version != STORY_SCHEMA_VERSION:
        raise ValueError(f"未対応のAxral Story schema_versionです: {version!r}")
    _str(doc.get("work_id"), "work_id"); _str(doc.get("title"), "title")
    if doc.get("kind") not in WORK_KINDS: raise ValueError("kindは対応する作品種別である必要があります。")
    if not isinstance(doc.get("chapters"), list): raise ValueError("chaptersは配列である必要があります。")
    ids: set[str] = set()
    def uid(value: Any, path: str) -> None:
        ident = _str(value, path)
        if not ident: raise ValueError(f"{path}は空にできません。")
        if ident in ids: raise ValueError(f"IDが重複しています: {ident}")
        ids.add(ident)
    for ci, cv in enumerate(doc["chapters"]):
        cp=f"chapters[{ci}]"; c=_obj(cv,cp); uid(c.get("id"),cp+".id"); _str(c.get("title"),cp+".title"); _order(c.get("order"),cp+".order",ci)
        if not isinstance(c.get("scenes"),list): raise ValueError(f"{cp}.scenesは配列である必要があります。")
        for si, sv in enumerate(c["scenes"]):
            sp=f"{cp}.scenes[{si}]"; s=_obj(sv,sp); uid(s.get("id"),sp+".id"); _str(s.get("title"),sp+".title"); _order(s.get("order"),sp+".order",si)
            if not isinstance(s.get("blocks"),list): raise ValueError(f"{sp}.blocksは配列である必要があります。")
            for bi,bv in enumerate(s["blocks"]):
                bp=f"{sp}.blocks[{bi}]"; b=_obj(bv,bp); uid(b.get("id"),bp+".id")
                if b.get("type") not in BLOCK_TYPES: raise ValueError(f"{bp}.typeは対応するブロック種別である必要があります。")
                _order(b.get("order"),bp+".order",bi); _str(b.get("text"),bp+".text")
                if b.get("character_id") is not None: _str(b["character_id"],bp+".character_id")
                refs=b.get("entity_refs",[])
                if not isinstance(refs,list) or not all(isinstance(r,str) for r in refs): raise ValueError(f"{bp}.entity_refsは文字列配列である必要があります。")
    return deepcopy(doc)

def serialize_story(payload: Any) -> str:
    return json.dumps(parse_story(payload), ensure_ascii=False, indent=2) + "\n"

def validate_story_references(payload: Any, known_entity_ids: set[str]) -> list[dict[str,str]]:
    """Report missing references; preserve them in the story payload."""
    story=parse_story(payload); findings=[]
    for ci,c in enumerate(story["chapters"]):
        for si,s in enumerate(c["scenes"]):
            for bi,b in enumerate(s["blocks"]):
                refs=list(b.get("entity_refs",[]))
                if b.get("character_id") is not None: refs.append(b["character_id"])
                for ref in refs:
                    if ref not in known_entity_ids:
                        findings.append({"path":f"chapters[{ci}].scenes[{si}].blocks[{bi}]","entity_id":ref,"message":f"参照先の世界設定IDが見つかりません: {ref}"})
    return findings
