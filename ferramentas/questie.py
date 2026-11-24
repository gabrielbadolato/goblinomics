"""Leitura da QuestieDB (base do addon Questie, GPL-3.0) para as ferramentas desta pasta.

Só lê arquivos de dados; não executa nada da QuestieDB. Monta as entidades do Forever na ordem da
própria base: dados brutos do Classic com coordenadas convertidas -> delta do Forever -> registros de
jogadores. As correções feitas à mão pelo Questie (forever*Fixes.lua) não são lidas.
"""
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lualit  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CAMPOS = {
    "Item": ["name", "npcDrops", "objectDrops", "itemDrops", "startQuest", "questRewards", "flags", "foodType",
             "itemLevel", "requiredLevel", "ammoType", "class", "subClass", "vendors", "relatedQuests"],
    "Object": ["name", "questStarts", "questEnds", "spawns", "zoneID"],
    "Npc": ["name", "minLevelHealth", "maxLevelHealth", "minLevel", "maxLevel", "rank", "spawns", "waypoints",
            "zoneID", "questStarts", "questEnds", "factionID", "friendlyToFaction", "subName", "npcFlags"],
}


def valores(v):
    return [x for x in (v.values() if isinstance(v, dict) else v or []) if x is not None]


def _bruto(arquivo, campos):
    t = arquivo.read_text(encoding="utf-8")
    d = lualit.tabela(t[t.index("[[return {") + 9: t.rindex("}]]") + 1])
    return {i: {c: v for c, v in zip(campos, lualit.lista(l)) if v is not None} | {"_era": True} for i, l in d.items()}


def _aplicar(base, arquivo):
    t = arquivo.read_text(encoding="utf-8")
    for i, campos in lualit.tabela(t[t.index("return {") + 7: t.rindex("}") + 1]).items():
        e = base.setdefault(i, {})
        for c, v in campos.items():
            if c.endswith("_add"):
                e[c[:-4]] = list(dict.fromkeys(valores(e.get(c[:-4])) + valores(v)))
            elif c.endswith("_remove"):
                e[c[:-7]] = [x for x in valores(e.get(c[:-7])) if x not in set(valores(v))]
            else:
                e[c] = v


def entidades(questie, tipo):
    """Itens ("Item"), objetos ("Object") ou NPCs ("Npc") do Forever: {id: {campo: valor, "_era": veio do Classic}}."""
    base = _bruto(questie / f"data/Forever/forever{tipo}DB.lua", CAMPOS[tipo])
    c = questie / "src/corrections/Forever"
    _aplicar(base, c / f"generated/foreverBase{tipo}.lua")
    _aplicar(base, c / f"traces/forever{tipo}Traces.lua")
    return base


def zonas(questie):
    """{id da zona: NOME_DO_ENUM} e o inverso."""
    pares = re.findall(r"^\s*([A-Z][A-Z0-9_]+)\s*=\s*(\d+)\s*,",
                       (questie / "src/corrections/enum/zones.lua").read_text(), re.M)
    por_id = {}
    for nome, i in pares:
        por_id.setdefault(int(i), nome)
    return por_id, {nome: int(i) for nome, i in pares}


def id_da_zona(valor, por_nome):
    """zoneID das correções vem como número ou como "@zoneIDs.NOME"."""
    if isinstance(valor, str):
        return por_nome.get(valor.split(".")[-1])
    return valor or None


def pontos(spawns):
    """{id da zona: quantos pontos} de um campo spawns."""
    return {z: len(lista) for z, lista in (spawns or {}).items() if isinstance(lista, dict) and isinstance(z, int)}


def versao(questie):
    return subprocess.run(["git", "-C", str(questie), "log", "-1", "--format=%h %ad", "--date=short"],
                          capture_output=True, text=True).stdout.strip()
