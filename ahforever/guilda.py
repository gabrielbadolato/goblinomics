import json
import os
import time
from datetime import datetime, timezone

ARQUIVO = "guildas.json"
# Profissões mudam devagar; uma leitura a cada 12 h basta.
HORAS = 12
AVULSOS = "avulsos"
# Personagens avulsos pedidos pelo bot do Discord (/personagem); somam-se aos do config.toml.
EXTRAS = "personagens_extra.json"


def caminho(cfg):
    return cfg.banco.parent / ARQUIVO


def _namespace(api):
    return f"profile-forever-{api.regiao}"


def ler(api, slug, sobrenome=False):
    """Membros da guilda com profissões e receitas conhecidas. None se a guilda não existe."""
    ns = _namespace(api)
    guilda = api.get(f"/data/wow/guild/{slug}", namespace=ns).dados
    if not guilda:
        return None
    lista = (api.get(f"/data/wow/guild/{slug}/roster", namespace=ns).dados or {}).get("members") or []
    membros = [m for m in (_membro(api, x["character"], sobrenome) for x in lista) if m]
    membros.sort(key=lambda m: m["nome"])
    return {"slug": slug, "nome": guilda["name"], "faccao": (guilda.get("faction") or {}).get("type"),
            "ruleset": (guilda.get("ruleset") or {}).get("id"), "lido_em": _agora(), "membros": membros}


def _agora():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _membro(api, c, sobrenome):
    """Profissões e receitas de um personagem; None se ele não tem nenhuma à mostra."""
    # Personagens de nível muito baixo respondem 404: ficam de fora.
    d = api.get(f"/profile/wow/character/{c['slug']}/professions", namespace=_namespace(api)).dados or {}
    profissoes, receitas = [], set()
    for p in (d.get("primaries") or []) + (d.get("secondaries") or []):
        camadas = p.get("tiers") or [p]
        profissoes.append([p["profession"]["id"], max(t.get("skill_points") or 0 for t in camadas)])
        for t in camadas:
            receitas.update(r["id"] for r in t.get("known_recipes") or [])
    if not profissoes:
        return None
    nome = c["name"] + (f" {c['surname']}" if sobrenome and c.get("surname") else "")
    return {"nome": nome, "nivel": c.get("level"), "profissoes": profissoes, "receitas": sorted(receitas)}


def ler_avulsos(api, slugs, sobrenome=False):
    """Personagens fora das guildas listadas, no mesmo formato de uma guilda (slug "avulsos")."""
    membros = []
    for slug in slugs:
        c = api.get(f"/profile/wow/character/{slug}", namespace=_namespace(api)).dados
        m = c and _membro(api, {**c, "slug": slug}, sobrenome)
        if not m:
            print(f"guilda: personagem {slug} não encontrado ou sem profissões")
            continue
        membros.append(m)
    membros.sort(key=lambda m: m["nome"])
    return {"slug": AVULSOS, "nome": "", "avulsos": True, "pedidos": list(slugs), "lido_em": _agora(),
            "membros": membros}


def atualizar(cfg, api, forcar=False):
    """Relê as guildas do config quando a última leitura envelheceu. Devolve se gravou."""
    arquivo = caminho(cfg)
    extras = cfg.banco.parent / EXTRAS
    personagens = list(dict.fromkeys(list(cfg.personagens) + (json.loads(extras.read_text()) if extras.exists() else [])))
    if not cfg.guildas and not personagens:
        arquivo.unlink(missing_ok=True)
        return False
    if not forcar and arquivo.exists():
        antigas = json.loads(arquivo.read_text())
        fresco = time.time() - arquivo.stat().st_mtime < HORAS * 3600
        pedidos = next((g["pedidos"] for g in antigas if g.get("avulsos")), [])
        if (fresco and [g["slug"] for g in antigas if not g.get("avulsos")] == cfg.guildas
                and pedidos == personagens):
            return False
    guildas = []
    for slug in cfg.guildas:
        g = ler(api, slug, cfg.sobrenome_na_guilda)
        if g is None:
            print(f"guilda: {slug} não encontrada")
            continue
        print(f"guilda: {g['nome']}, {len(g['membros'])} membros com profissão")
        guildas.append(g)
    if personagens:
        avulsos = ler_avulsos(api, personagens, cfg.sobrenome_na_guilda)
        print(f"guilda: {len(avulsos['membros'])} personagens avulsos")
        guildas.append(avulsos)
    temporario = arquivo.with_suffix(".tmp")
    temporario.write_text(json.dumps(guildas, ensure_ascii=False, separators=(",", ":")))
    os.replace(temporario, arquivo)
    return True
