"""Outline and block editing operations for Axral Story v1; source is never mutated."""
from __future__ import annotations
from copy import deepcopy
from typing import Any
from .story import parse_story

def _copy(value: Any) -> dict[str, Any]: return parse_story(deepcopy(value))
def _chapter(story: dict[str, Any], ident: str) -> dict[str, Any]:
    for item in story["chapters"]:
        if item["id"] == ident: return item
    raise ValueError(f"章が見つかりません: {ident}")
def _scene(story: dict[str, Any], ident: str) -> dict[str, Any]:
    for chapter in story["chapters"]:
        for item in chapter["scenes"]:
            if item["id"] == ident: return item
    raise ValueError(f"シーンが見つかりません: {ident}")
def _block_owner(story: dict[str, Any], ident: str) -> dict[str, Any]:
    for chapter in story["chapters"]:
        for scene in chapter["scenes"]:
            if any(item["id"] == ident for item in scene["blocks"]): return scene
    raise ValueError(f"ブロックが見つかりません: {ident}")
def _reorder(items: list[dict[str, Any]], source: int, target: int) -> None:
    if isinstance(target,bool) or not isinstance(target,int) or target<0 or target>=len(items): raise ValueError("移動先の順序が範囲外です。")
    items.insert(target,items.pop(source))
    for i,item in enumerate(items): item["order"]=i
def add_chapter(value: Any, ident: str, title: str) -> dict[str, Any]:
    s=_copy(value);s["chapters"].append({"id":ident,"title":title,"order":len(s["chapters"]),"scenes":[]});return parse_story(s)
def rename_chapter(value: Any, ident: str, title: str) -> dict[str, Any]:
    s=_copy(value);_chapter(s,ident)["title"]=title;return parse_story(s)
def reorder_chapter(value: Any, ident: str, target: int) -> dict[str, Any]:
    s=_copy(value);items=s["chapters"];i=next((i for i,x in enumerate(items) if x["id"]==ident),-1)
    if i<0: raise ValueError(f"章が見つかりません: {ident}")
    _reorder(items,i,target);return parse_story(s)
def delete_chapter(value: Any, ident: str) -> dict[str, Any]:
    s=_copy(value);items=s["chapters"];i=next((i for i,x in enumerate(items) if x["id"]==ident),-1)
    if i<0: raise ValueError(f"章が見つかりません: {ident}")
    items.pop(i)
    for n,x in enumerate(items):x["order"]=n
    return parse_story(s)
def add_scene(value: Any, chapter_id: str, ident: str, title: str) -> dict[str, Any]:
    s=_copy(value);c=_chapter(s,chapter_id);c["scenes"].append({"id":ident,"title":title,"order":len(c["scenes"]),"blocks":[]});return parse_story(s)
def rename_scene(value: Any, ident: str, title: str) -> dict[str, Any]:
    s=_copy(value);_scene(s,ident)["title"]=title;return parse_story(s)
def reorder_scene(value: Any, ident: str, target: int) -> dict[str, Any]:
    s=_copy(value)
    for c in s["chapters"]:
        items=c["scenes"];i=next((i for i,x in enumerate(items) if x["id"]==ident),-1)
        if i>=0:_reorder(items,i,target);return parse_story(s)
    raise ValueError(f"シーンが見つかりません: {ident}")
def delete_scene(value: Any, ident: str) -> dict[str, Any]:
    s=_copy(value)
    for c in s["chapters"]:
        items=c["scenes"];i=next((i for i,x in enumerate(items) if x["id"]==ident),-1)
        if i>=0:
            items.pop(i)
            for n,x in enumerate(items):x["order"]=n
            return parse_story(s)
    raise ValueError(f"シーンが見つかりません: {ident}")
def add_block(value: Any, scene_id: str, block: dict[str, Any]) -> dict[str, Any]:
    s=_copy(value);scene=_scene(s,scene_id);item=deepcopy(block);item["order"]=len(scene["blocks"]);scene["blocks"].append(item);return parse_story(s)
def update_block(value: Any, ident: str, changes: dict[str, Any]) -> dict[str, Any]:
    if not set(changes).issubset({"type","text","character_id","entity_refs"}):raise ValueError("変更できないブロック項目が含まれています。")
    s=_copy(value);scene=_block_owner(s,ident);next(x for x in scene["blocks"] if x["id"]==ident).update(changes);return parse_story(s)
def reorder_block(value: Any, ident: str, target: int) -> dict[str, Any]:
    s=_copy(value);scene=_block_owner(s,ident);items=scene["blocks"];i=next(i for i,x in enumerate(items) if x["id"]==ident);_reorder(items,i,target);return parse_story(s)
def delete_block(value: Any, ident: str) -> dict[str, Any]:
    s=_copy(value);scene=_block_owner(s,ident);items=scene["blocks"];i=next(i for i,x in enumerate(items) if x["id"]==ident);items.pop(i)
    for n,x in enumerate(items):x["order"]=n
    return parse_story(s)
